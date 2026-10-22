from stock import services
from stock.models import Vente


def vendre(reference_id, quantite, vendeur, **kwargs):
    """Enregistre une vente ; en boutique, payée par carte bancaire sauf indication contraire."""
    if kwargs.get("canal", Vente.Canal.MAGASIN) == Vente.Canal.MAGASIN:
        kwargs.setdefault("paiement", Vente.Paiement.CB)
    return services.enregistrer_vente(reference_id, quantite, vendeur, **kwargs)
