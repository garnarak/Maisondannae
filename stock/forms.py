from decimal import Decimal

from django import forms

from .models import FOND_DE_CAISSE, REMISES, Ajustement, Couleur, Modele, Taille, Vente


class ModeleForm(forms.ModelForm):
    class Meta:
        model = Modele
        fields = ["categorie", "nom", "cout_achat", "prix_vente", "active"]
        labels = {"nom": "Désignation", "active": "Actif"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categorie"].required = True
        self.fields["categorie"].empty_label = "— Choisir une catégorie —"


class VariantesForm(forms.Form):
    tailles = forms.MultipleChoiceField(
        choices=Taille.choices, widget=forms.CheckboxSelectMultiple, required=False,
        help_text="« Taille unique » pour un article sans taille.",
    )
    couleurs = forms.ModelMultipleChoiceField(
        queryset=Couleur.objects.all(), widget=forms.CheckboxSelectMultiple, required=False,
        help_text="Aucune couleur cochée : une seule variante par taille, sans couleur.",
    )

    def __init__(self, *args, obligatoire=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.obligatoire = obligatoire

    def clean_tailles(self):
        tailles = self.cleaned_data["tailles"]
        if Taille.TU in tailles and len(tailles) > 1:
            raise forms.ValidationError("« Taille unique » ne se combine pas avec d'autres tailles.")
        if self.obligatoire and not tailles:
            raise forms.ValidationError("Cochez au moins une taille (ou « Taille unique »).")
        return tailles


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
