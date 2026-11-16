"""Couplage avec la boutique Shopify.

- Outil → Shopify : quantités en stock et prix des variantes, liées par leur SKU.
- Shopify → outil : commandes (ventes en ligne), annulations et remboursements avec remise en stock,
  reçus par notifications signées (webhooks).

Le couplage est inactif tant que SHOPIFY_SHOP et une clé d'accès ne sont pas renseignés sur Render.
Toutes les requêtes passent par `ClientShopify.transport`, que les tests remplacent par une boutique
simulée.
"""

import base64
import hashlib
import hmac
import json
import logging
import threading
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction

from .models import ORDRE_TAILLES, CommandeShopify, EvenementShopify, Modele, Reference, Taille, Vente

journal = logging.getLogger(__name__)
TAILLE_LOT = 25  # variantes par requête


class ErreurShopify(Exception):
    pass


def _transport_http(methode, url, entetes, corps):
    requete = urllib.request.Request(url, data=corps, headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, reponse.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErreurShopify(f"Shopify injoignable : {e}") from e


class ClientShopify:
    transport = staticmethod(_transport_http)

    @staticmethod
    def actif():
        return bool(settings.SHOPIFY_SHOP and (
            settings.SHOPIFY_ACCESS_TOKEN or (settings.SHOPIFY_CLIENT_ID and settings.SHOPIFY_CLIENT_SECRET)
        ))

    def _jeton(self):
        if settings.SHOPIFY_ACCESS_TOKEN:
            return settings.SHOPIFY_ACCESS_TOKEN
        # Application du Dev Dashboard : jeton temporaire obtenu avec l'identifiant et le secret.
        jeton = cache.get("shopify_jeton")
        if jeton:
            return jeton
        corps = json.dumps({
            "grant_type": "client_credentials",
            "client_id": settings.SHOPIFY_CLIENT_ID,
            "client_secret": settings.SHOPIFY_CLIENT_SECRET,
        }).encode()
        statut, reponse = self.transport(
            "POST", f"https://{settings.SHOPIFY_SHOP}/admin/oauth/access_token",
            {"Content-Type": "application/json", "Accept": "application/json"}, corps,
        )
        if statut != 200:
            raise ErreurShopify(f"Connexion refusée par Shopify (code {statut}) : vérifiez l'identifiant et le secret.")
        donnees = json.loads(reponse)
        cache.set("shopify_jeton", donnees["access_token"], max(60, int(donnees.get("expires_in", 3600)) - 300))
        return donnees["access_token"]

    def graphql(self, requete, variables=None):
        url = f"https://{settings.SHOPIFY_SHOP}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
        entetes = {"Content-Type": "application/json", "X-Shopify-Access-Token": self._jeton()}
        statut, reponse = self.transport("POST", url, entetes, json.dumps({"query": requete, "variables": variables or {}}).encode())
        if statut in (401, 403):
            raise ErreurShopify(f"Accès refusé par Shopify (code {statut}) : vérifiez la clé et ses autorisations.")
        if statut != 200:
            raise ErreurShopify(f"Erreur Shopify (code {statut}).")
        donnees = json.loads(reponse)
        if donnees.get("errors"):
            raise ErreurShopify("Erreur Shopify : " + "; ".join(e.get("message", str(e)) for e in donnees["errors"]))
        return donnees["data"]


def _verifier_erreurs(resultat, action):
    erreurs = (resultat or {}).get("userErrors") or []
    if erreurs:
        raise ErreurShopify(f"{action} : " + "; ".join(e.get("message", "") for e in erreurs))


def journaliser(sens, action, statut, message="", webhook_id=""):
    return EvenementShopify.objects.create(sens=sens, action=action, statut=statut, message=message[:2000],
                                           webhook_id=webhook_id)


# --- Requêtes GraphQL (Admin API) -------------------------------------------------------------------

Q_BOUTIQUE = "query Boutique { shop { name } locations(first: 10) { nodes { id name } } }"
Q_VARIANTES = """query VariantesParSku($q: String!) {
  productVariants(first: 100, query: $q) { nodes { id sku product { id } inventoryItem { id } } }
}"""
M_STOCK = """mutation StockAJour($input: InventorySetQuantitiesInput!, $cle: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $cle) { userErrors { field message } }
}"""
# Forme des versions d'API plus anciennes (sans clé d'idempotence ni changeFromQuantity).
M_STOCK_ANCIEN = """mutation StockAJour($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) { userErrors { field message } }
}"""
M_PRIX = """mutation PrixAJour($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) { userErrors { field message } }
}"""
M_PRODUIT = """mutation CreerProduit($input: ProductSetInput!) {
  productSet(synchronous: true, input: $input) {
    product { id variants(first: 100) { nodes { id sku inventoryItem { id } } } }
    userErrors { field message }
  }
}"""


def _emplacement(client):
    if settings.SHOPIFY_LOCATION_ID:
        return settings.SHOPIFY_LOCATION_ID
    emplacement = cache.get("shopify_emplacement")
    if not emplacement:
        noeuds = client.graphql(Q_BOUTIQUE)["locations"]["nodes"]
        if not noeuds:
            raise ErreurShopify("Aucun emplacement de stock dans la boutique Shopify.")
        emplacement = noeuds[0]["id"]
        cache.set("shopify_emplacement", emplacement, 3600)
    return emplacement


def tester_connexion(client=None):
    client = client or ClientShopify()
    donnees = client.graphql(Q_BOUTIQUE)
    return donnees["shop"]["name"], [e["name"] for e in donnees["locations"]["nodes"]]


def lier_variantes(variantes, client=None):
    """Retrouve dans Shopify les variantes de même SKU et mémorise leurs identifiants."""
    client = client or ClientShopify()
    a_lier = [v for v in variantes if v.sku and not v.shopify_inventory_item_id]
    for i in range(0, len(a_lier), TAILLE_LOT):
        lot = {v.sku: v for v in a_lier[i:i + TAILLE_LOT]}
        q = " OR ".join(f'sku:"{sku}"' for sku in lot)
        for n in client.graphql(Q_VARIANTES, {"q": q})["productVariants"]["nodes"]:
            v = lot.get(n.get("sku"))
            if v:
                v.shopify_variant_id, v.shopify_inventory_item_id = n["id"], n["inventoryItem"]["id"]
                Reference.objects.filter(pk=v.pk).update(
                    shopify_variant_id=v.shopify_variant_id, shopify_inventory_item_id=v.shopify_inventory_item_id
                )


def pousser_stock(ids, client=None):
    """Envoie à Shopify la quantité en stock des variantes données. Ne lève jamais d'exception :
    un échec est noté dans le journal et la variante est marquée « à resynchroniser »."""
    if not ClientShopify.actif() or not ids:
        return
    client = client or ClientShopify()
    variantes = list(Reference.objects.filter(pk__in=ids))
    try:
        lier_variantes(variantes, client)
        liees = [v for v in variantes if v.shopify_inventory_item_id]
        if liees:
            emplacement = _emplacement(client)
            for i in range(0, len(liees), TAILLE_LOT):
                _envoyer_quantites(client, emplacement, liees[i:i + TAILLE_LOT])
        Reference.objects.filter(pk__in=[v.pk for v in liees]).update(shopify_a_synchroniser=False)
        absentes = [v.designation for v in variantes if not v.shopify_inventory_item_id]
        message = ", ".join(f"{v.designation} : {v.quantite}" for v in liees)
        if absentes:
            message += (" — absentes de Shopify : " if message else "Absentes de Shopify : ") + ", ".join(absentes)
        journaliser(EvenementShopify.Sens.ENVOI, "Stock", EvenementShopify.Statut.OK if liees else EvenementShopify.Statut.IGNORE, message)
    except ErreurShopify as e:
        Reference.objects.filter(pk__in=ids).update(shopify_a_synchroniser=True)
        journaliser(EvenementShopify.Sens.ENVOI, "Stock", EvenementShopify.Statut.ERREUR, str(e))


def _envoyer_quantites(client, emplacement, variantes):
    """Fixe la quantité disponible dans Shopify. L'outil fait foi : pas de comparaison avec la
    quantité que Shopify croit avoir (changeFromQuantity nul)."""
    quantites = [{"inventoryItemId": v.shopify_inventory_item_id, "locationId": emplacement, "quantity": v.quantite}
                 for v in variantes]
    try:
        resultat = client.graphql(M_STOCK, {"cle": str(uuid.uuid4()), "input": {
            "name": "available", "reason": "correction",
            "quantities": [{**q, "changeFromQuantity": None} for q in quantites],
        }})["inventorySetQuantities"]
    except ErreurShopify as e:
        if not any(mot in str(e) for mot in ("idempotent", "changeFromQuantity", "compare")):
            raise
        resultat = client.graphql(M_STOCK_ANCIEN, {"input": {
            "name": "available", "reason": "correction", "ignoreCompareQuantity": True, "quantities": quantites,
        }})["inventorySetQuantities"]
    _verifier_erreurs(resultat, "Mise à jour du stock")


def pousser_prix(modele_id, client=None):
    """Envoie à Shopify le prix d'un modèle pour toutes ses variantes liées."""
    if not ClientShopify.actif():
        return
    client = client or ClientShopify()
    modele = Modele.objects.get(pk=modele_id)
    variantes = list(modele.variantes.all())
    try:
        lier_variantes(variantes, client)
        par_produit = {}
        for v in variantes:
            if v.shopify_variant_id:
                produit = _produit_de(client, v)
                par_produit.setdefault(produit, []).append({"id": v.shopify_variant_id, "price": str(modele.prix_vente)})
        for produit, lignes in par_produit.items():
            _verifier_erreurs(client.graphql(M_PRIX, {"productId": produit, "variants": lignes})["productVariantsBulkUpdate"],
                              "Mise à jour du prix")
        if par_produit:
            journaliser(EvenementShopify.Sens.ENVOI, "Prix", EvenementShopify.Statut.OK, f"{modele} : {modele.prix_vente} €")
    except ErreurShopify as e:
        modele.variantes.update(shopify_a_synchroniser=True)
        journaliser(EvenementShopify.Sens.ENVOI, "Prix", EvenementShopify.Statut.ERREUR, f"{modele} : {e}")


def _produit_de(client, variante):
    cle = f"shopify_produit_{variante.shopify_variant_id}"
    produit = cache.get(cle)
    if not produit:
        noeuds = client.graphql(Q_VARIANTES, {"q": f'sku:"{variante.sku}"'})["productVariants"]["nodes"]
        produit = next((n["product"]["id"] for n in noeuds if n["id"] == variante.shopify_variant_id), None)
        if not produit:
            raise ErreurShopify(f"Produit Shopify introuvable pour {variante}.")
        cache.set(cle, produit, 24 * 3600)
    return produit


def creer_produits_manquants(client=None):
    """Crée en brouillon dans Shopify les modèles dont aucune variante n'y existe encore,
    avec tailles, couleurs, prix, SKU et quantités. Renvoie le nombre de produits créés."""
    client = client or ClientShopify()
    variantes = list(Reference.objects.filter(active=True).select_related("modele", "couleur"))
    lier_variantes(variantes, client)
    emplacement = _emplacement(client)
    par_modele = {}
    for v in variantes:
        par_modele.setdefault(v.modele, []).append(v)
    crees = 0
    for modele, vs in par_modele.items():
        if any(v.shopify_variant_id for v in vs):
            continue  # déjà dans Shopify (au moins en partie) : on ne crée pas de doublon
        vs.sort(key=lambda v: (ORDRE_TAILLES.get(v.taille, 99), v.couleur.nom if v.couleur else ""))
        tailles = list(dict.fromkeys(v.get_taille_display() for v in vs))
        couleurs = list(dict.fromkeys(v.couleur.nom for v in vs if v.couleur))
        options = [{"name": "Taille", "values": [{"name": t} for t in tailles]}]
        if couleurs:
            options.append({"name": "Couleur", "values": [{"name": c} for c in couleurs]})

        def valeurs(v):
            o = [{"optionName": "Taille", "name": v.get_taille_display()}]
            if couleurs:
                o.append({"optionName": "Couleur", "name": v.couleur.nom if v.couleur else "Sans couleur"})
            return o

        resultat = client.graphql(M_PRODUIT, {"input": {
            "title": modele.nom, "status": "DRAFT",
            "productType": modele.categorie.nom if modele.categorie else "",
            "productOptions": options,
            "variants": [{
                "optionValues": valeurs(v), "price": str(modele.prix_vente),
                "inventoryItem": {"sku": v.sku, "tracked": True},
                "inventoryQuantities": [{"locationId": emplacement, "name": "available", "quantity": v.quantite}],
            } for v in vs],
        }})["productSet"]
        _verifier_erreurs(resultat, f"Création de « {modele} »")
        par_sku = {v.sku: v for v in vs}
        for n in resultat["product"]["variants"]["nodes"]:
            if n.get("sku") in par_sku:
                Reference.objects.filter(pk=par_sku[n["sku"]].pk).update(
                    shopify_variant_id=n["id"], shopify_inventory_item_id=n["inventoryItem"]["id"],
                    shopify_a_synchroniser=False,
                )
        crees += 1
        journaliser(EvenementShopify.Sens.ENVOI, "Création de produit", EvenementShopify.Statut.OK,
                    f"{modele} ({len(vs)} variante(s)), en brouillon")
    return crees


def resynchroniser_tout(client=None):
    """Renvoie le stock de toutes les variantes et le prix de tous les modèles."""
    client = client or ClientShopify()
    pousser_stock(list(Reference.objects.values_list("pk", flat=True)), client)
    for modele_id in Modele.objects.values_list("pk", flat=True):
        pousser_prix(modele_id, client)


_en_attente = threading.local()


def _envoyer(stock, prix):
    try:
        if stock:
            pousser_stock(sorted(stock))
        for modele_id in sorted(prix):
            pousser_prix(modele_id)
    except Exception:  # noqa: BLE001 — un envoi raté ne doit jamais bloquer une vente
        journal.exception("Envoi vers Shopify")
        Reference.objects.filter(pk__in=stock).update(shopify_a_synchroniser=True)


def _vider_file():
    stock, prix = getattr(_en_attente, "stock", set()), getattr(_en_attente, "prix", set())
    if not (stock or prix):
        return  # déjà envoyé par un rappel précédent de la même opération
    _en_attente.stock, _en_attente.prix = set(), set()
    if not settings.SHOPIFY_EN_ARRIERE_PLAN:
        _envoyer(stock, prix)
        return

    def tache():
        try:
            _envoyer(stock, prix)
        finally:
            connection.close()

    threading.Thread(target=tache, daemon=True).start()


def _signaler(stock=(), prix=()):
    """Programme l'envoi vers Shopify une fois l'opération enregistrée en base. Les variantes et
    modèles touchés par une même opération (entrée en stock, import Excel…) partent ensemble,
    en tâche de fond pour ne pas ralentir l'écran de vente. Après une opération annulée, ce qui
    restait en attente part avec l'envoi suivant (renvoyer une quantité juste est sans effet)."""
    if not ClientShopify.actif():
        return
    if not hasattr(_en_attente, "stock"):
        _en_attente.stock, _en_attente.prix = set(), set()
    _en_attente.stock.update(stock)
    _en_attente.prix.update(prix)
    transaction.on_commit(_vider_file)  # immédiat hors transaction


def signaler_stock(*reference_ids):
    _signaler(stock=reference_ids)


def signaler_prix(modele_id):
    _signaler(prix=[modele_id])


# --- Notifications reçues de Shopify (webhooks) ------------------------------------------------------

def signature_valide(corps, signature):
    if not settings.SHOPIFY_WEBHOOK_SECRET or not signature:
        return False
    attendu = base64.b64encode(hmac.new(settings.SHOPIFY_WEBHOOK_SECRET.encode(), corps, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(attendu, signature)


def _variante_pour(ligne):
    sku = (ligne.get("sku") or "").strip()
    if sku:
        v = Reference.objects.filter(sku__iexact=sku).first()
        if v:
            return v
    variant_id = ligne.get("variant_id")
    if variant_id:
        return Reference.objects.filter(shopify_variant_id__endswith=f"/{variant_id}").first()
    return None


@transaction.atomic
def traiter_commande(donnees):
    """Commande créée sur Shopify : une vente en ligne par ligne, stock diminué."""
    from . import services

    commande, creee = CommandeShopify.objects.get_or_create(
        shopify_id=str(donnees["id"]),
        defaults={"nom": donnees.get("name") or str(donnees["id"]),
                  "date": donnees.get("created_at") or donnees.get("processed_at")},
    )
    if not creee:
        return "Commande déjà enregistrée.", EvenementShopify.Statut.IGNORE
    notes, erreur = [], False
    for ligne in donnees.get("line_items", []):
        quantite = int(ligne.get("quantity") or 0)
        if quantite <= 0:
            continue
        v = _variante_pour(ligne)
        if v is None:
            erreur = True
            notes.append(f"SKU « {ligne.get('sku') or '—'} » ({ligne.get('title', '')}) inconnu : vente non enregistrée")
            continue
        prix = Decimal(str(ligne.get("price") or "0")) - Decimal(str(ligne.get("total_discount") or "0")) / quantite
        disponible = Reference.objects.get(pk=v.pk).quantite
        if disponible < quantite:
            erreur = True
            notes.append(f"{v} : {quantite} commandée(s), {disponible} en stock")
            quantite = disponible
        if not quantite:
            signaler_stock(v.pk)  # remet Shopify d'accord avec le stock réel
        else:
            services.enregistrer_vente_en_ligne(v.pk, quantite, prix.quantize(Decimal("0.01")), commande,
                                                str(ligne.get("id", "")))
            notes.append(f"{quantite} × {v}")
    statut = EvenementShopify.Statut.ERREUR if erreur else EvenementShopify.Statut.OK
    return f"Commande {commande} : " + ("; ".join(notes) or "aucune ligne"), statut


@transaction.atomic
def traiter_annulation(donnees):
    """Commande annulée sur Shopify : ses ventes sont annulées et les articles reviennent en stock."""
    from . import services

    commande = CommandeShopify.objects.filter(shopify_id=str(donnees["id"])).first()
    if commande is None:
        return "Commande inconnue de l'outil.", EvenementShopify.Statut.IGNORE
    if commande.annulee:
        return f"Commande {commande} déjà annulée.", EvenementShopify.Statut.IGNORE
    ventes = list(commande.ventes.all())
    for vente in ventes:
        services.annuler_vente(vente.pk)
    commande.annulee = True
    commande.save(update_fields=["annulee"])
    return f"Commande {commande} annulée : {len(ventes)} vente(s) annulée(s), articles remis en stock.", EvenementShopify.Statut.OK


@transaction.atomic
def traiter_remboursement(donnees):
    """Remboursement sur Shopify : les pièces remises en stock (retour ou annulation) reviennent
    en stock et la vente est réduite d'autant. Un remboursement sans remise en stock ne change rien."""
    from . import services

    notes = []
    for ligne in donnees.get("refund_line_items", []):
        if ligne.get("restock_type") == "no_restock":
            continue
        vente = Vente.objects.filter(ligne_shopify=str(ligne.get("line_item_id"))).first()
        if vente is None:
            continue
        quantite = min(int(ligne.get("quantity") or 0), vente.quantite)
        if quantite:
            services.retour_partiel(vente.pk, quantite)
            notes.append(f"{quantite} × {vente.reference} remis en stock")
    if not notes:
        return "Remboursement sans remise en stock.", EvenementShopify.Statut.IGNORE
    return "Remboursement : " + "; ".join(notes), EvenementShopify.Statut.OK


TRAITEMENTS = {
    "orders/create": ("Commande", traiter_commande),
    "orders/cancelled": ("Annulation", traiter_annulation),
    "refunds/create": ("Remboursement", traiter_remboursement),
}


def recevoir_notification(sujet, webhook_id, donnees):
    """Traite une notification déjà authentifiée. Une même notification reçue deux fois
    (Shopify réessaie en cas de doute) n'est traitée qu'une fois."""
    if webhook_id and EvenementShopify.objects.filter(webhook_id=webhook_id).exclude(statut=EvenementShopify.Statut.ERREUR).exists():
        return
    action, traitement = TRAITEMENTS.get(sujet, (sujet, None))
    if traitement is None:
        journaliser(EvenementShopify.Sens.RECEPTION, action, EvenementShopify.Statut.IGNORE, "Notification non gérée.", webhook_id)
        return
    try:
        message, statut = traitement(donnees)
    except Exception as e:  # noqa: BLE001 — une notification mal formée ne doit jamais faire planter le site
        journal.exception("Notification Shopify %s", sujet)
        message, statut = f"Erreur de traitement : {e}", EvenementShopify.Statut.ERREUR
    journaliser(EvenementShopify.Sens.RECEPTION, action, statut, message, webhook_id)


# --- Abonnement aux notifications --------------------------------------------------------------------

Q_ABONNEMENTS = """query Abonnements { webhookSubscriptions(first: 50) { nodes { id topic uri } } }"""
M_ABONNER = """mutation Abonner($topic: WebhookSubscriptionTopic!, $uri: String!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: {uri: $uri, format: JSON}) {
    webhookSubscription { id } userErrors { field message }
  }
}"""
SUJETS = {"orders/create": "ORDERS_CREATE", "orders/cancelled": "ORDERS_CANCELLED", "refunds/create": "REFUNDS_CREATE"}


def abonner_notifications(adresse, client=None):
    """Demande à Shopify de prévenir l'outil (à l'adresse donnée) des commandes, annulations et
    remboursements. Renvoie le nombre d'abonnements créés (ceux déjà en place sont gardés)."""
    client = client or ClientShopify()
    existants = {(n["topic"], n.get("uri")) for n in client.graphql(Q_ABONNEMENTS)["webhookSubscriptions"]["nodes"]}
    crees = 0
    for topic in SUJETS.values():
        if (topic, adresse) in existants:
            continue
        _verifier_erreurs(client.graphql(M_ABONNER, {"topic": topic, "uri": adresse})["webhookSubscriptionCreate"],
                          f"Abonnement {topic}")
        crees += 1
    journaliser(EvenementShopify.Sens.ENVOI, "Abonnement aux notifications", EvenementShopify.Statut.OK,
                f"{crees} abonnement(s) créé(s) vers {adresse}")
    return crees
