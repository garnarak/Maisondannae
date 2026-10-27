from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import FOND_DE_CAISSE, REMISES, Ajustement, RecuperationEspeces, Reference, Vente, prix_remise


class StockInsuffisant(Exception):
    pass


class PaiementInvalide(Exception):
    pass


def _montant_especes(total, paiement, montant_especes):
    """Part en espèces d'une vente en boutique, selon le mode de paiement choisi."""
    if paiement == Vente.Paiement.ESPECES:
        return total
    if paiement == Vente.Paiement.CB:
        return Decimal(0)
    if paiement == Vente.Paiement.MIXTE:
        if montant_especes is None or not (Decimal(0) < montant_especes < total):
            raise PaiementInvalide(
                f"Pour un paiement en espèces + CB, le montant en espèces doit être compris "
                f"entre 0 et {total} €."
            )
        return montant_especes
    raise PaiementInvalide("Choisissez le mode de paiement : espèces, carte bancaire ou les deux.")


@transaction.atomic
def enregistrer_vente(
    reference_id, quantite, vendeur, canal=Vente.Canal.MAGASIN, remise_pct=0, paiement="", montant_especes=None
):
    if remise_pct != 0 and remise_pct not in REMISES:
        raise ValueError(f"Solde non autorisé : {remise_pct} %")
    ref = Reference.objects.select_for_update().get(pk=reference_id)
    if quantite > ref.quantite:
        raise StockInsuffisant(f"Stock insuffisant : {ref.quantite} en stock.")
    prix = prix_remise(ref.prix_vente, remise_pct)
    if canal == Vente.Canal.MAGASIN:
        especes = _montant_especes(prix * quantite, paiement, montant_especes)
    else:
        # Vente en ligne : payée en ligne, rien n'entre dans la caisse.
        paiement, especes = "", Decimal(0)
    Reference.objects.filter(pk=ref.pk).update(quantite=F("quantite") - quantite)
    return Vente.objects.create(
        reference=ref,
        quantite=quantite,
        prix_catalogue=ref.prix_vente,
        remise_pct=remise_pct,
        prix_unitaire=prix,
        paiement=paiement,
        montant_especes=especes,
        cout_unitaire=ref.cout_achat,
        canal=canal,
        # Les ventes en ligne ne sont attribuées à aucun vendeur.
        vendeur=None if canal == Vente.Canal.EN_LIGNE else vendeur,
        saisie_par=vendeur,
    )


@transaction.atomic
def annuler_vente(vente_id):
    vente = Vente.objects.select_for_update().get(pk=vente_id)
    Reference.objects.filter(pk=vente.reference_id).update(quantite=F("quantite") + vente.quantite)
    vente.delete()


@transaction.atomic
def ajuster_stock(reference_id, variation, motif, utilisateur, commentaire=""):
    ref = Reference.objects.select_for_update().get(pk=reference_id)
    if ref.quantite + variation < 0:
        raise StockInsuffisant(f"Le stock ne peut pas devenir négatif ({ref.quantite} en stock).")
    Reference.objects.filter(pk=ref.pk).update(quantite=F("quantite") + variation)
    return Ajustement.objects.create(
        reference=ref, variation=variation, motif=motif, utilisateur=utilisateur, commentaire=commentaire
    )


def derniere_recuperation():
    return RecuperationEspeces.objects.order_by("-date").first()


def especes_en_caisse():
    """Espèces théoriquement dans la caisse : fond laissé à la dernière récupération
    (30 € avant la toute première) + espèces encaissées depuis."""
    derniere = derniere_recuperation()
    ventes = Vente.objects.all()
    if derniere:
        fond = derniere.fond_laisse
        ventes = ventes.filter(date__gt=derniere.date)
    else:
        fond = FOND_DE_CAISSE
    return fond + (ventes.aggregate(t=Sum("montant_especes"))["t"] or Decimal(0))


@transaction.atomic
def recuperer_especes(administrateur, fond_laisse=FOND_DE_CAISSE):
    if not getattr(administrateur, "is_admin", False):
        raise PermissionError("Seul un administrateur peut récupérer les espèces.")
    # Verrou : deux récupérations simultanées ne doivent pas compter deux fois les mêmes espèces.
    list(RecuperationEspeces.objects.select_for_update().all()[:1])
    en_caisse = especes_en_caisse()
    if fond_laisse < 0 or fond_laisse > en_caisse:
        raise PaiementInvalide(f"Le fond laissé doit être compris entre 0 et {en_caisse} €.")
    return RecuperationEspeces.objects.create(
        date=timezone.now(),
        administrateur=administrateur,
        especes_en_caisse=en_caisse,
        fond_laisse=fond_laisse,
        montant_recupere=en_caisse - fond_laisse,
    )
