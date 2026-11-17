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
    # Seules les couleurs simples sont proposées : en cocher deux crée une variante bicolore.
    couleurs = forms.ModelMultipleChoiceField(
        queryset=Couleur.objects.exclude(nom__contains="/"), widget=forms.CheckboxSelectMultiple, required=False,
        help_text="Une couleur : variante de cette couleur. Deux couleurs : variante bicolore (ex. Blanc / Terracotta), "
                  "dans l'ordre où vous les cochez. Aucune : variante sans couleur.",
    )
    # Ordre dans lequel les couleurs ont été cochées (rempli par la page) : « Blanc / Terracotta »
    # et non « Terracotta / Blanc » si l'on a cliqué Blanc en premier.
    ordre_couleurs = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, obligatoire=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.obligatoire = obligatoire

    def clean(self):
        """Renvoie dans « couleurs » la couleur de la variante : aucune, une simple, ou la
        couleur double formée des deux couleurs cochées (créée au besoin, sans apparaître
        dans les pastilles)."""
        donnees = super().clean()
        couleurs = list(donnees.get("couleurs") or [])
        if len(couleurs) > 2:
            raise forms.ValidationError("Cochez au plus deux couleurs : une pour une variante unie, deux pour une variante bicolore.")
        if len(couleurs) == 2:
            ordre = [p for p in (donnees.get("ordre_couleurs") or "").split(",") if p.isdigit()]
            couleurs.sort(key=lambda c: (ordre.index(str(c.pk)) if str(c.pk) in ordre else len(ordre), c.nom))
            double, _ = Couleur.objects.get_or_create(nom=f"{couleurs[0].nom} / {couleurs[1].nom}"[:40])
            donnees["couleurs"] = [double]
        return donnees

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
