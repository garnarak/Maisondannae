from django.db import transaction
from django.db.models import F

from .models import Ajustement, Reference, Vente


class StockInsuffisant(Exception):
    pass


@transaction.atomic
def enregistrer_vente(reference_id, quantite, vendeur, canal=Vente.Canal.MAGASIN):
    ref = Reference.objects.select_for_update().get(pk=reference_id)
    if quantite > ref.quantite:
        raise StockInsuffisant(f"Stock insuffisant : {ref.quantite} en stock.")
    Reference.objects.filter(pk=ref.pk).update(quantite=F("quantite") - quantite)
    return Vente.objects.create(
        reference=ref,
        quantite=quantite,
        prix_unitaire=ref.prix_vente,
        cout_unitaire=ref.cout_achat,
        canal=canal,
        vendeur=vendeur,
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
