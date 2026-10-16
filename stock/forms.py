from django import forms

from .models import Ajustement, Reference


class ReferenceForm(forms.ModelForm):
    class Meta:
        model = Reference
        fields = ["designation", "cout_achat", "prix_vente", "quantite", "active"]


class ReferenceEditForm(forms.ModelForm):
    """La quantité ne se modifie pas ici : elle passe par une vente ou un ajustement tracé."""

    class Meta:
        model = Reference
        fields = ["designation", "cout_achat", "prix_vente", "active"]


class VenteForm(forms.Form):
    quantite = forms.IntegerField(min_value=1, initial=1, label="Quantité")


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
