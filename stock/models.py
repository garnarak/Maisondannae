from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


# Pourcentages de solde proposés au vendeur au moment de la vente.
REMISES = [10, 20, 30, 40, 50, 70]


def prix_remise(prix, remise_pct):
    """Prix après application d'un pourcentage de solde, arrondi au centime."""
    return (prix * (100 - remise_pct) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        RESTREINT = "restreint", "Restreint"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESTREINT)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        # Seuls les administrateurs accèdent à l'interface d'administration Django.
        self.is_staff = self.role == self.Role.ADMIN
        super().save(*args, **kwargs)


class Reference(models.Model):
    designation = models.CharField("désignation", max_length=200, unique=True)
    cout_achat = models.DecimalField(
        "coût d'achat", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    prix_vente = models.DecimalField(
        "prix de vente", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    quantite = models.PositiveIntegerField("quantité en stock", default=0)
    active = models.BooleanField(default=True, help_text="Décocher pour masquer une référence arrêtée.")
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["designation"]
        verbose_name = "référence"

    def __str__(self):
        return self.designation

    @property
    def marge_unitaire(self):
        return self.prix_vente - self.cout_achat

    @property
    def prix_soldes(self):
        return [(pct, prix_remise(self.prix_vente, pct)) for pct in REMISES]


class Vente(models.Model):
    class Canal(models.TextChoices):
        MAGASIN = "magasin", "Magasin"
        EN_LIGNE = "en_ligne", "En ligne"

    reference = models.ForeignKey(Reference, on_delete=models.PROTECT, related_name="ventes")
    date = models.DateTimeField(default=timezone.now, db_index=True)
    quantite = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    # Prix et coût figés au moment de la vente : la marge passée ne bouge pas
    # si l'on modifie ensuite la référence.
    prix_catalogue = models.DecimalField(
        "prix de vente initial", max_digits=10, decimal_places=2,
        help_text="Prix de la référence au moment de la vente, avant solde.",
    )
    remise_pct = models.PositiveSmallIntegerField(
        "solde (%)", default=0, choices=[(0, "Aucun")] + [(p, f"{p} %") for p in REMISES]
    )
    prix_unitaire = models.DecimalField(
        "prix encaissé", max_digits=10, decimal_places=2, help_text="Prix après solde."
    )
    cout_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.MAGASIN)
    vendeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ventes"
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.quantite} × {self.reference} ({self.date:%d/%m/%Y})"

    def save(self, *args, **kwargs):
        if self.prix_catalogue is None:
            self.prix_catalogue = self.prix_unitaire
        super().save(*args, **kwargs)

    @property
    def chiffre_affaires(self):
        return self.prix_unitaire * self.quantite

    @property
    def marge(self):
        return (self.prix_unitaire - self.cout_unitaire) * self.quantite

    @property
    def montant_remise(self):
        return (self.prix_catalogue - self.prix_unitaire) * self.quantite


class Ajustement(models.Model):
    """Mouvement de stock hors vente (réassort, inventaire, casse…). N'entre pas dans la marge."""

    class Motif(models.TextChoices):
        REASSORT = "reassort", "Réassort / réception"
        INVENTAIRE = "inventaire", "Correction d'inventaire"
        CASSE = "casse", "Casse / perte"
        RETOUR = "retour", "Retour client"
        AUTRE = "autre", "Autre"

    reference = models.ForeignKey(Reference, on_delete=models.CASCADE, related_name="ajustements")
    date = models.DateTimeField(default=timezone.now)
    variation = models.IntegerField(help_text="Positif pour une entrée, négatif pour une sortie.")
    motif = models.CharField(max_length=20, choices=Motif.choices)
    commentaire = models.CharField(max_length=200, blank=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-date"]
