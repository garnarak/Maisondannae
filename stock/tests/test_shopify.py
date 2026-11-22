import base64
import hashlib
import hmac
import json
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from stock import services, shopify
from stock.models import Ajustement, CommandeShopify, Couleur, EvenementShopify, Modele, Reference, User, Vente

from .outils import vendre

SECRET = "secret-de-test"
CONFIG = dict(
    SHOPIFY_SHOP="boutique-test.myshopify.com", SHOPIFY_ACCESS_TOKEN="", SHOPIFY_CLIENT_ID="id",
    SHOPIFY_CLIENT_SECRET=SECRET, SHOPIFY_WEBHOOK_SECRET=SECRET, SHOPIFY_LOCATION_ID="",
    SHOPIFY_EN_ARRIERE_PLAN=False,
)


class FausseBoutique:
    """Boutique Shopify simulée : répond aux requêtes de l'outil et les garde en mémoire."""

    def __init__(self):
        self.variantes = {}  # sku -> {"id", "inventory", "product", "price", "quantite"}
        self.requetes = []
        self.panne = False
        self.abonnements = []
        self.ancienne_api = False
        self.statuts = {}  # produit -> ACTIVE / DRAFT / ARCHIVED

    def ajouter(self, sku, produit="gid://shopify/Product/1", statut="ACTIVE"):
        self.statuts.setdefault(produit, statut)
        n = len(self.variantes) + 1
        self.variantes[sku] = {"id": f"gid://shopify/ProductVariant/{n}", "inventory": f"gid://shopify/InventoryItem/{n}",
                               "product": produit, "price": None, "quantite": None}

    def noms(self):
        return [r["nom"] for r in self.requetes]

    def __call__(self, methode, url, entetes, corps):
        if self.panne:
            raise shopify.ErreurShopify("Shopify injoignable : panne simulée")
        if url.endswith("/oauth/access_token"):
            return 200, json.dumps({"access_token": "jeton", "expires_in": 86399}).encode()
        assert entetes["X-Shopify-Access-Token"] == "jeton"
        demande = json.loads(corps)
        q, v = demande["query"], demande["variables"]
        nom = q.split("{")[0].split()[1].split("(")[0]
        self.requetes.append({"nom": nom, "variables": v})
        if nom == "Boutique":
            data = {"shop": {"name": "Maison test"}, "locations": {"nodes": [{"id": "gid://shopify/Location/9", "name": "Boutique"}]}}
        elif nom == "VariantesParSku":
            skus = [s.split('"')[1] for s in v["q"].split(" OR ")]
            data = {"productVariants": {"nodes": [
                {"id": x["id"], "sku": s, "product": {"id": x["product"]}, "inventoryItem": {"id": x["inventory"]}}
                for s, x in self.variantes.items() if s in skus]}}
        elif nom == "StockAJour" and self.ancienne_api and "@idempotent" in q:
            return 200, json.dumps({"errors": [{"message": "Directive 'idempotent' doesn't exist"}]}).encode()
        elif nom == "StockAJour":
            assert ("@idempotent" in q) == ("cle" in v) and ("ignoreCompareQuantity" in v["input"]) != ("@idempotent" in q)
            par_item = {x["inventory"]: x for x in self.variantes.values()}
            for ligne in v["input"]["quantities"]:
                par_item[ligne["inventoryItemId"]]["quantite"] = ligne["quantity"]
            data = {"inventorySetQuantities": {"userErrors": []}}
        elif nom == "PrixAJour":
            par_id = {x["id"]: x for x in self.variantes.values()}
            for ligne in v["variants"]:
                par_id[ligne["id"]]["price"] = ligne["price"]
            data = {"productVariantsBulkUpdate": {"userErrors": []}}
        elif nom == "CreerProduit":
            produit = f"gid://shopify/Product/{100 + len(self.requetes)}"
            for ligne in v["input"]["variants"]:
                self.ajouter(ligne["inventoryItem"]["sku"], produit, v["input"]["status"])
                self.variantes[ligne["inventoryItem"]["sku"]]["quantite"] = ligne["inventoryQuantities"][0]["quantity"]
            data = {"productSet": {"userErrors": [], "product": {"id": produit, "variants": {"nodes": [
                {"id": self.variantes[l["inventoryItem"]["sku"]]["id"], "sku": l["inventoryItem"]["sku"],
                 "inventoryItem": {"id": self.variantes[l["inventoryItem"]["sku"]]["inventory"]}} for l in v["input"]["variants"]]}}}}
        elif nom == "Statuts":
            data = {"nodes": [{"id": i, "status": self.statuts[i]} if i in self.statuts else None for i in v["ids"]]}
        elif nom == "Statut":
            self.statuts[v["product"]["id"]] = v["product"]["status"]
            data = {"productUpdate": {"userErrors": []}}
        elif nom == "Abonnements":
            data = {"webhookSubscriptions": {"nodes": [{"id": "x", "topic": t, "uri": u} for t, u in self.abonnements]}}
        elif nom == "Abonner":
            self.abonnements.append((v["topic"], v["uri"]))
            data = {"webhookSubscriptionCreate": {"userErrors": [], "webhookSubscription": {"id": "w"}}}
        else:
            raise AssertionError(nom)
        return 200, json.dumps({"data": data}).encode()


@override_settings(**CONFIG)
class BaseShopify(TestCase):
    def setUp(self):
        cache.clear()
        self.boutique = FausseBoutique()
        patch = mock.patch.object(shopify.ClientShopify, "transport", staticmethod(self.boutique))
        patch.start()
        self.addCleanup(patch.stop)
        self.admin = User.objects.create_user("admin", password="x", role=User.Role.ADMIN)
        self.vendeuse = User.objects.create_user("lea", password="x", role=User.Role.RESTREINT)
        self.noir, _ = Couleur.objects.get_or_create(nom="Noir")
        self.modele = services.creer_modele("Robe portefeuille", None, Decimal("20"), Decimal("60"), ["S", "M"], [self.noir])
        self.s, self.m = self.modele.variantes.order_by("taille")[1], self.modele.variantes.order_by("taille")[0]
        services.entree_en_stock({self.s.pk: 3, self.m.pk: 2}, self.admin)
        shopify._en_attente.__dict__.clear()  # envois programmés par la préparation : non exécutés
        self.boutique.requetes.clear()
        self.boutique.ajouter(self.s.sku)
        self.boutique.ajouter(self.m.sku)

    def stock_shopify(self, variante):
        return self.boutique.variantes[variante.sku]["quantite"]


class EnvoiVersShopify(BaseShopify):
    def test_une_vente_en_boutique_met_a_jour_le_stock_shopify(self):
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 1, self.vendeuse)
        self.assertEqual(self.stock_shopify(self.s), 2)
        self.s.refresh_from_db()
        self.assertTrue(self.s.shopify_inventory_item_id)
        self.assertEqual(EvenementShopify.objects.filter(statut="ok", action="Stock").count(), 1)

    def test_annulation_et_ajustement_aussi(self):
        with self.captureOnCommitCallbacks(execute=True):
            vente = vendre(self.m.pk, 2, self.vendeuse)
        self.assertEqual(self.stock_shopify(self.m), 0)
        with self.captureOnCommitCallbacks(execute=True):
            services.annuler_vente(vente.pk)
        self.assertEqual(self.stock_shopify(self.m), 2)
        with self.captureOnCommitCallbacks(execute=True):
            services.ajuster_stock(self.m.pk, 5, Ajustement.Motif.REASSORT, self.admin)
        self.assertEqual(self.stock_shopify(self.m), 7)

    def test_une_entree_en_stock_part_en_une_seule_requete(self):
        with self.captureOnCommitCallbacks(execute=True):
            services.entree_en_stock({self.s.pk: 1, self.m.pk: 1}, self.admin)
        self.assertEqual(self.boutique.noms().count("StockAJour"), 1)
        self.assertEqual((self.stock_shopify(self.s), self.stock_shopify(self.m)), (4, 3))

    def test_version_d_api_plus_ancienne(self):
        self.boutique.ancienne_api = True
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 1, self.vendeuse)
        self.assertEqual(self.stock_shopify(self.s), 2)

    def test_rien_n_est_envoye_si_l_operation_echoue(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(services.StockInsuffisant):
                vendre(self.s.pk, 10, self.vendeuse)
        self.assertEqual(self.boutique.requetes, [])

    def test_changement_de_prix_envoye(self):
        self.modele.prix_vente = Decimal("55.00")
        with self.captureOnCommitCallbacks(execute=True):
            self.modele.save()
        self.assertEqual(self.boutique.variantes[self.s.sku]["price"], "55.00")
        self.assertEqual(self.boutique.variantes[self.m.sku]["price"], "55.00")

    def test_meme_prix_rien_n_est_envoye(self):
        self.modele.nom = "Robe portefeuille longue"
        with self.captureOnCommitCallbacks(execute=True):
            self.modele.save()
        self.assertNotIn("PrixAJour", self.boutique.noms())

    def test_variante_absente_de_shopify_ignoree(self):
        autre = services.creer_modele("Foulard", None, Decimal("5"), Decimal("15"), ["TU"], [])
        v = autre.variantes.get()
        with self.captureOnCommitCallbacks(execute=True):
            services.ajuster_stock(v.pk, 1, Ajustement.Motif.REASSORT, self.admin)
        e = EvenementShopify.objects.latest("date")
        self.assertEqual(e.statut, "ignore")
        self.assertIn("Foulard", e.message)

    def test_panne_shopify_la_vente_est_quand_meme_enregistree(self):
        self.boutique.panne = True
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 1, self.vendeuse)
        self.s.refresh_from_db()
        self.assertEqual(self.s.quantite, 2)
        self.assertTrue(self.s.shopify_a_synchroniser)
        self.assertEqual(EvenementShopify.objects.latest("date").statut, "erreur")
        # Le renvoi complet répare l'écart une fois Shopify revenu.
        self.boutique.panne = False
        shopify.resynchroniser_tout()
        self.s.refresh_from_db()
        self.assertFalse(self.s.shopify_a_synchroniser)
        self.assertEqual(self.stock_shopify(self.s), 2)

    @override_settings(SHOPIFY_SHOP="")
    def test_inactif_sans_configuration(self):
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 1, self.vendeuse)
        self.assertEqual(self.boutique.requetes, [])
        self.assertFalse(EvenementShopify.objects.exists())

    def test_nouveau_sku_le_lien_est_recherche_a_nouveau(self):
        shopify.pousser_stock([self.s.pk])
        self.s.refresh_from_db()
        self.s.sku = "NOUVEAU-SKU"
        self.s.save()
        self.assertEqual(self.s.shopify_variant_id, "")


class ArchivageAutomatique(BaseShopify):
    """Option B (2.2.0) : un modèle épuisé est archivé dans Shopify, puis remis comme avant s'il revient."""

    PRODUIT = "gid://shopify/Product/1"

    def tout_vendre(self):
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 3, self.vendeuse)
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.m.pk, 2, self.vendeuse)

    def test_epuise_puis_de_retour(self):
        with self.captureOnCommitCallbacks(execute=True):
            vendre(self.s.pk, 3, self.vendeuse)
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ACTIVE")  # il reste du M
        with self.captureOnCommitCallbacks(execute=True):
            vente = vendre(self.m.pk, 2, self.vendeuse)
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ARCHIVED")
        self.modele.refresh_from_db()
        self.assertEqual((self.modele.shopify_product_id, self.modele.shopify_statut_avant_archivage), (self.PRODUIT, "ACTIVE"))
        self.assertTrue(EvenementShopify.objects.filter(action="Archivage").exists())
        # Vente annulée : la pièce revient, le produit est remis en ligne.
        with self.captureOnCommitCallbacks(execute=True):
            services.annuler_vente(vente.pk)
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ACTIVE")
        self.modele.refresh_from_db()
        self.assertEqual(self.modele.shopify_statut_avant_archivage, "")

    def test_un_brouillon_redevient_brouillon(self):
        self.boutique.statuts[self.PRODUIT] = "DRAFT"
        self.tout_vendre()
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ARCHIVED")
        with self.captureOnCommitCallbacks(execute=True):
            services.entree_en_stock({self.s.pk: 1}, self.admin)
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "DRAFT")

    def test_un_produit_archive_a_la_main_n_est_pas_remis_en_ligne(self):
        self.boutique.statuts[self.PRODUIT] = "ARCHIVED"
        with self.captureOnCommitCallbacks(execute=True):
            services.entree_en_stock({self.s.pk: 1}, self.admin)
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ARCHIVED")
        self.assertNotIn("Statut", self.boutique.noms())

    def test_commande_en_ligne_de_la_derniere_piece(self):
        services.ajuster_stock(self.s.pk, -3, Ajustement.Motif.INVENTAIRE, self.admin)
        corps = json.dumps(commande(lignes=[{"id": 1, "sku": self.m.sku, "title": "Robe", "quantity": 2, "price": "60"}])).encode()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("shopify_notifications"), corps, content_type="application/json",
                             HTTP_X_SHOPIFY_TOPIC="orders/create", HTTP_X_SHOPIFY_WEBHOOK_ID="w1",
                             HTTP_X_SHOPIFY_HMAC_SHA256=signer(corps))
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ARCHIVED")

    def test_le_renvoi_complet_archive_les_epuises_deja_dans_shopify(self):
        Reference.objects.filter(pk__in=[self.s.pk, self.m.pk]).update(quantite=0)  # épuisés avant 2.2.0
        shopify.resynchroniser_tout()
        self.assertEqual(self.boutique.statuts[self.PRODUIT], "ARCHIVED")
        self.assertTrue(EvenementShopify.objects.filter(action="Renvoi complet", statut="ok").exists())

    def test_les_modeles_epuises_ne_sont_pas_crees(self):
        self.boutique.variantes.clear()
        Reference.objects.filter(pk__in=[self.s.pk, self.m.pk]).update(quantite=0)
        self.assertEqual(shopify.creer_produits_manquants(), (0, 0))
        self.assertNotIn("CreerProduit", self.boutique.noms())


class CreationDeProduits(BaseShopify):
    def test_cree_en_brouillon_les_modeles_absents(self):
        self.boutique.variantes.clear()
        n, incomplets = shopify.creer_produits_manquants()
        self.assertEqual((n, incomplets), (1, 0))
        creation = next(r for r in self.boutique.requetes if r["nom"] == "CreerProduit")["variables"]["input"]
        self.assertEqual(creation["status"], "DRAFT")
        self.assertEqual(creation["title"], "Robe portefeuille")
        self.assertEqual([o["name"] for o in creation["productOptions"]], ["Taille", "Couleur"])
        self.assertEqual(self.stock_shopify(self.s), 3)
        self.s.refresh_from_db()
        self.assertTrue(self.s.shopify_variant_id)
        # Deuxième passage : rien à créer, pas de doublon.
        self.assertEqual(shopify.creer_produits_manquants(), (0, 0))

    def test_produit_supprime_dans_shopify_recree(self):
        self.boutique.variantes.clear()
        shopify.creer_produits_manquants()
        self.boutique.variantes.clear()  # produit supprimé à la main dans Shopify
        self.assertEqual(shopify.creer_produits_manquants(), (1, 0))
        self.s.refresh_from_db()
        self.assertEqual(self.s.shopify_variant_id, self.boutique.variantes[self.s.sku]["id"])

    def test_article_a_taille_unique_decline_ensuite(self):
        foulard = services.creer_modele("Foulard", None, Decimal("5"), Decimal("15"), ["TU"], [])
        unique = foulard.variantes.get()
        services.ajuster_stock(unique.pk, 1, Ajustement.Motif.REASSORT, self.admin)
        self.assertEqual(shopify.creer_produits_manquants(), (1, 0))
        # Le foulard existe finalement en deux couleurs : la variante unique vidée est masquée…
        services.ajuster_stock(unique.pk, -1, Ajustement.Motif.INVENTAIRE, self.admin)
        rouge, _ = Couleur.objects.get_or_create(nom="Rouge")
        services.ajouter_variantes(foulard, ["TU"], [self.noir])
        services.ajouter_variantes(foulard, ["TU"], [rouge])
        for v in foulard.variantes.exclude(pk=unique.pk):
            services.ajuster_stock(v.pk, 1, Ajustement.Motif.REASSORT, self.admin)
        unique.refresh_from_db()
        self.assertFalse(unique.active)
        # … et le produit Shopify à taille unique est signalé, sans être créé en double.
        self.assertEqual(shopify.creer_produits_manquants(), (0, 1))
        self.assertIn("Foulard", EvenementShopify.objects.get(action="Variantes absentes de Shopify").message)
        # Une fois ce produit supprimé dans Shopify, il est recréé avec ses couleurs.
        del self.boutique.variantes[unique.sku]
        self.assertEqual(shopify.creer_produits_manquants(), (1, 0))
        creation = [r for r in self.boutique.requetes if r["nom"] == "CreerProduit"][-1]["variables"]["input"]
        self.assertEqual(len(creation["variants"]), 2)

    def test_variante_unique_avec_stock_reste_visible(self):
        foulard = services.creer_modele("Foulard", None, Decimal("5"), Decimal("15"), ["TU"], [])
        unique = foulard.variantes.get()
        services.ajuster_stock(unique.pk, 2, Ajustement.Motif.REASSORT, self.admin)
        services.ajouter_variantes(foulard, ["S", "M"], [])
        unique.refresh_from_db()
        self.assertTrue(unique.active)
        # Une fois son stock réparti et remis à 0, elle est masquée.
        services.ajuster_stock(unique.pk, -2, Ajustement.Motif.INVENTAIRE, self.admin)
        unique.refresh_from_db()
        self.assertFalse(unique.active)

    def test_historique_intact_quand_la_taille_unique_est_masquee(self):
        foulard = services.creer_modele("Foulard", None, Decimal("5"), Decimal("15"), ["TU"], [])
        unique = foulard.variantes.get()
        services.ajuster_stock(unique.pk, 1, Ajustement.Motif.REASSORT, self.admin)
        vente = vendre(unique.pk, 1, self.vendeuse)
        services.ajouter_variantes(foulard, ["S", "M"], [])
        unique.refresh_from_db()
        self.assertFalse(unique.active)
        # Ventes, marge et export Excel comptent toujours la vente de l'ancienne variante.
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("ventes")), "Foulard")
        self.assertContains(self.client.get(reverse("marge")), "Foulard")
        # Si cette vente est annulée, la pièce revient en stock et la variante réapparaît.
        services.annuler_vente(vente.pk)
        unique.refresh_from_db()
        self.assertTrue(unique.active)
        self.assertEqual(unique.quantite, 1)

    def test_ne_recree_pas_un_modele_deja_dans_shopify(self):
        self.assertEqual(shopify.creer_produits_manquants(), (0, 0))
        self.assertNotIn("CreerProduit", self.boutique.noms())


def signer(corps):
    return base64.b64encode(hmac.new(SECRET.encode(), corps, hashlib.sha256).digest()).decode()


def commande(id_=1001, lignes=None):
    return {"id": id_, "name": f"#{id_}", "created_at": "2026-11-16T10:00:00+01:00", "line_items": lignes or []}


@override_settings(**CONFIG)
class ReceptionDesCommandes(BaseShopify):
    def notifier(self, sujet, donnees, webhook_id="w1", signature=None):
        corps = json.dumps(donnees).encode()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("shopify_notifications"), corps, content_type="application/json",
                HTTP_X_SHOPIFY_TOPIC=sujet, HTTP_X_SHOPIFY_WEBHOOK_ID=webhook_id,
                HTTP_X_SHOPIFY_HMAC_SHA256=signature if signature is not None else signer(corps),
            )

    def ligne(self, variante, quantite=1, prix="60.00", remise="0.00", id_=1):
        return {"id": id_, "sku": variante.sku, "title": "Robe", "quantity": quantite, "price": prix, "total_discount": remise}

    def test_commande_enregistree_en_vente_en_ligne(self):
        r = self.notifier("orders/create", commande(lignes=[self.ligne(self.s, 2, remise="12.00")]))
        self.assertEqual(r.status_code, 200)
        vente = Vente.objects.get()
        self.assertEqual((vente.canal, vente.quantite, vente.prix_unitaire), (Vente.Canal.EN_LIGNE, 2, Decimal("54.00")))
        self.assertIsNone(vente.vendeur)
        self.assertEqual(vente.prix_catalogue, Decimal("60.00"))
        self.assertEqual(vente.montant_especes, 0)
        self.s.refresh_from_db()
        self.assertEqual(self.s.quantite, 1)
        self.assertEqual(vente.commande_shopify.nom, "#1001")

    def test_signature_fausse_refusee(self):
        r = self.notifier("orders/create", commande(lignes=[self.ligne(self.s)]), signature="faux")
        self.assertEqual(r.status_code, 401)
        self.assertFalse(Vente.objects.exists())

    def test_meme_commande_recue_deux_fois(self):
        donnees = commande(lignes=[self.ligne(self.s)])
        self.notifier("orders/create", donnees, webhook_id="w1")
        self.notifier("orders/create", donnees, webhook_id="w1")
        self.notifier("orders/create", donnees, webhook_id="w2")
        self.assertEqual(Vente.objects.count(), 1)

    def test_sku_inconnu_note_en_erreur(self):
        self.notifier("orders/create", commande(lignes=[{"id": 5, "sku": "XYZ", "title": "Sac", "quantity": 1, "price": "10"}]))
        self.assertFalse(Vente.objects.exists())
        e = EvenementShopify.objects.get(sens="reception")
        self.assertEqual(e.statut, "erreur")
        self.assertIn("XYZ", e.message)

    def test_stock_insuffisant_vend_ce_qui_reste(self):
        self.notifier("orders/create", commande(lignes=[self.ligne(self.m, 5)]))
        self.assertEqual(Vente.objects.get().quantite, 2)
        self.assertEqual(EvenementShopify.objects.get(sens="reception").statut, "erreur")

    def test_annulation_remet_en_stock(self):
        self.notifier("orders/create", commande(lignes=[self.ligne(self.s, 2)]), webhook_id="w1")
        self.notifier("orders/cancelled", {"id": 1001}, webhook_id="w2")
        self.assertFalse(Vente.objects.exists())
        self.s.refresh_from_db()
        self.assertEqual(self.s.quantite, 3)
        self.assertTrue(CommandeShopify.objects.get().annulee)
        self.assertEqual(self.stock_shopify(self.s), 3)

    def test_remboursement_partiel_avec_retour(self):
        self.notifier("orders/create", commande(lignes=[self.ligne(self.s, 2, id_=77)]), webhook_id="w1")
        self.notifier("refunds/create", {"id": 9, "order_id": 1001, "refund_line_items": [
            {"line_item_id": 77, "quantity": 1, "restock_type": "return"}]}, webhook_id="w2")
        self.assertEqual(Vente.objects.get().quantite, 1)
        self.s.refresh_from_db()
        self.assertEqual(self.s.quantite, 2)

    def test_remboursement_sans_retour_ne_change_rien(self):
        self.notifier("orders/create", commande(lignes=[self.ligne(self.s, 2, id_=77)]), webhook_id="w1")
        self.notifier("refunds/create", {"id": 9, "refund_line_items": [
            {"line_item_id": 77, "quantity": 1, "restock_type": "no_restock"}]}, webhook_id="w2")
        self.assertEqual(Vente.objects.get().quantite, 2)

    def test_les_ventes_shopify_apparaissent_dans_ventes_en_ligne(self):
        self.notifier("orders/create", commande(lignes=[self.ligne(self.s)]))
        self.client.force_login(self.admin)
        r = self.client.get(reverse("ventes_en_ligne"))
        self.assertContains(r, "Robe portefeuille")


@override_settings(**CONFIG)
class PageAdministration(BaseShopify):
    def test_reservee_aux_administrateurs(self):
        self.client.force_login(self.vendeuse)
        self.assertNotEqual(self.client.get(reverse("shopify_accueil")).status_code, 200)

    def test_page_et_actions(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("shopify_accueil"))
        self.assertContains(r, "boutique-test.myshopify.com")
        r = self.client.post(reverse("shopify_action", args=["tester"]), follow=True)
        self.assertContains(r, "Maison test")
        r = self.client.post(reverse("shopify_action", args=["abonner"]), follow=True)
        self.assertContains(r, "3 abonnement")
        self.assertTrue(all(u.endswith("/shopify/notifications/") for _, u in self.boutique.abonnements))
        r = self.client.post(reverse("shopify_action", args=["abonner"]), follow=True)
        self.assertContains(r, "0 abonnement")
        r = self.client.post(reverse("shopify_action", args=["resynchroniser"]), follow=True)
        self.assertEqual(self.stock_shopify(self.s), 3)

    @override_settings(SHOPIFY_SHOP="")
    def test_non_configure(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("shopify_accueil"))
        self.assertContains(r, "non configuré")
