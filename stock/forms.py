from decimal import Decimal

from django import forms

from .models import FOND_DE_CAISSE, REMISES, Ajustement, Reference, Vente


class CategorieObligatoireMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categorie"].required = True
        self.fields["categorie"].empty_label = "— Choisir une catégorie —"


class ReferenceForm(CategorieObligatoireMixin, forms.ModelForm):
    class Meta:
        model = Reference
        fields = ["designation", "categorie", "cout_achat", "prix_vente", "quantite", "active"]


class ReferenceEditForm(CategorieObligatoireMixin, forms.ModelForm):
    """La quantité ne se modifie pas ici : elle passe par une vente ou un ajustement tracé."""

    class Meta:
        model = Reference
        fields = ["designation", "categorie", "cout_achat", "prix_vente", "active"]


class VenteForm(forms.Form):
    quantite = forms.IntegerField(min_value=1, initial=1, label="Quantité")
    remise_pct = forms.TypedChoiceField(
        label="Solde",
        choices=[(0, "Prix normal")] + [(p, f"−{p} %") for p in REMISES],
        coerce=int,
        initial=0,
        required=False,
        empty_value=0,
    )
    canal = forms.ChoiceField(choices=Vente.Canal.choices, initial=Vente.Canal.MAGASIN, required=False)

    def clean_canal(self):
        return self.cleaned_data["canal"] or Vente.Canal.MAGASIN


class PaiementForm(VenteForm):
    paiement = forms.ChoiceField(choices=Vente.Paiement.choices)
    montant_especes = forms.DecimalField(
        label="Montant payé en espèces", min_value=Decimal("0.01"), max_digits=10, decimal_places=2, required=False
    )


class RecuperationForm(forms.Form):
    fond_laisse = forms.DecimalField(
        label="Montant laissé dans la caisse", min_value=0, max_digits=10, decimal_places=2,
        initial=FOND_DE_CAISSE,
    )


class AjustementForm(forms.Form):
    variation = forms.IntegerField(
        label="Variation", help_text="Ex. : 5 pour une réception, -1 pour une casse."
    )
    motif = forms.ChoiceField(choices=Ajustement.Motif.choices)
    commentaire = forms.CharField(max_length=200, required=False)

    def clean_variation(self):
        v = self.cleaned_data["variation"]
        if v == 0:
            raise forms.ValidationError("La variation ne peut pas être nulle.")
        return v
