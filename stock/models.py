from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


# À partir de combien de pièces restantes un article est signalé « stock faible ».
SEUIL_STOCK_FAIBLE = 2

# Pourcentages de solde proposés au vendeur au moment de la vente.
REMISES = [10, 15, 20, 25, 30, 40, 50, 70]


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


class Categorie(models.Model):
    """Catégorie d'article (Veste, Pantalon…). La liste se gère depuis l'administration."""

    nom = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "catégorie"

    def __str__(self):
        return self.nom


# Tailles en lettres, dans l'ordre d'affichage. « TU » = taille unique.
class Taille(models.TextChoices):
    TU = "TU", "Taille unique"
    XS = "XS", "XS"
    S = "S", "S"
    M = "M", "M"
    L = "L", "L"
    XL = "XL", "XL"
    XXL = "XXL", "XXL"


ORDRE_TAILLES = {valeur: i for i, valeur in enumerate(Taille.values)}


class Couleur(models.Model):
    """Couleur proposée dans la liste déroulante. La liste se gère depuis l'administration."""

    nom = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Modele(models.Model):
    """Un article tel que la cliente le voit (« Robe portefeuille »). Son prix et son coût
    valent pour toutes ses variantes de taille et de couleur."""

    nom = models.CharField(max_length=160, unique=True)
    categorie = models.ForeignKey(
        Categorie, on_delete=models.PROTECT, null=True, blank=True, related_name="modeles",
        verbose_name="catégorie",
    )
    cout_achat = models.DecimalField(
        "coût d'achat", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    prix_vente = models.DecimalField(
        "prix de vente", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    active = models.BooleanField(default=True, help_text="Décocher pour masquer un modèle arrêté.")
    # Produit Shopify correspondant, et son statut d'avant l'archivage automatique (vide si
    # l'outil ne l'a pas archivé) : un modèle épuisé est archivé, puis remis comme avant s'il revient.
    shopify_product_id = models.CharField(max_length=80, blank=True, editable=False)
    shopify_statut_avant_archivage = models.CharField(max_length=20, blank=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "modèle"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        avant = Modele.objects.filter(pk=self.pk).values("active", "prix_vente").first() if self.pk else None
        ancien = avant["active"] if avant else None
        super().save(*args, **kwargs)
        if avant and avant["prix_vente"] != self.prix_vente:
            from . import shopify  # import tardif : shopify importe les modèles

            shopify.signaler_prix(self.pk)
        # Les variantes recopient nom, catégorie, coût et prix du modèle ; masquer ou
        # réafficher le modèle masque ou réaffiche toutes ses variantes.
        for variante in self.variantes.all():
            if ancien is not None and ancien != self.active:
                variante.active = self.active
            variante.save()


class Reference(models.Model):
    """Une variante d'un modèle (taille × couleur) : c'est l'unité de stock et de vente."""

    modele = models.ForeignKey(Modele, on_delete=models.PROTECT, null=True, related_name="variantes")
    taille = models.CharField(max_length=4, choices=Taille.choices, default=Taille.TU)
    couleur = models.ForeignKey(Couleur, on_delete=models.PROTECT, null=True, blank=True, related_name="variantes")
    sku = models.CharField(
        "SKU", max_length=40, unique=True, null=True, blank=True,
        help_text="Code commun avec la boutique en ligne. Généré automatiquement s'il est vide.",
    )
    # Lien avec la variante Shopify de même SKU, renseigné à la première synchronisation.
    shopify_variant_id = models.CharField(max_length=80, blank=True, editable=False)
    shopify_inventory_item_id = models.CharField(max_length=80, blank=True, editable=False)
    # Vrai quand le dernier envoi du stock ou du prix vers Shopify a échoué : à renvoyer.
    shopify_a_synchroniser = models.BooleanField(default=False, editable=False)
    # Recopiés du modèle à chaque enregistrement (voir save) : les listes, filtres et
    # calculs de marge s'appuient dessus.
    designation = models.CharField("désignation", max_length=200, unique=True)
    # Obligatoire dans les formulaires ; vide possible seulement pour les références
    # créées avant l'ajout des catégories.
    categorie = models.ForeignKey(
        Categorie, on_delete=models.PROTECT, null=True, blank=True, related_name="references",
        verbose_name="catégorie",
    )
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
        verbose_name = "variante"

    def __str__(self):
        return self.designation

    @property
    def libelle_variante(self):
        """« M · Noir », « Taille unique », « Écru »…"""
        morceaux = [] if self.taille == Taille.TU else [self.taille]
        if self.couleur_id:
            morceaux.append(self.couleur.nom)
        return " · ".join(morceaux) or "Taille unique"

    @property
    def est_unique(self):
        return self.taille == Taille.TU and not self.couleur_id

    def save(self, *args, **kwargs):
        if not self.modele_id:
            # Article créé sans modèle : il devient un modèle à taille unique.
            self.modele = Modele.objects.create(
                nom=self.designation, categorie_id=self.categorie_id, cout_achat=self.cout_achat,
                prix_vente=self.prix_vente, active=self.active,
            )
        if self.modele_id:
            m = self.modele
            self.categorie_id, self.cout_achat, self.prix_vente = m.categorie_id, m.cout_achat, m.prix_vente
            if self.pk is None and not m.active:
                self.active = False
            self.designation = m.nom if self.est_unique else f"{m.nom} — {self.libelle_variante}"
            if not self.sku:
                self.sku = self._sku_libre(f"MA{m.pk:04d}-{self.taille}-{self._code_couleur()}")
        if self.pk and self.shopify_variant_id:
            ancien_sku = Reference.objects.filter(pk=self.pk).values_list("sku", flat=True).first()
            if ancien_sku != self.sku:  # nouveau SKU : le lien Shopify sera recherché à nouveau
                self.shopify_variant_id = self.shopify_inventory_item_id = ""
        super().save(*args, **kwargs)

    def _code_couleur(self):
        if not self.couleur_id:
            return "U"
        parties = [p for p in self.couleur.nom.split("/") if p.strip()]
        if len(parties) > 1:  # couleur double : « Blanc / Terracotta » → BLA-TER
            return "-".join(slugify(p)[:3].upper() for p in parties)
        return slugify(self.couleur.nom)[:6].upper().strip("-")

    def _sku_libre(self, sku):
        """Deux couleurs aux noms proches peuvent donner le même code : on numérote."""
        candidat, n = sku, 2
        while Reference.objects.filter(sku=candidat).exclude(pk=self.pk).exists():
            candidat, n = f"{sku}{n}", n + 1
        return candidat

    @property
    def marge_unitaire(self):
        return self.prix_vente - self.cout_achat

    @property
    def prix_soldes(self):
        return [(pct, prix_remise(self.prix_vente, pct)) for pct in REMISES]


class Vente(models.Model):
    class Canal(models.TextChoices):
        MAGASIN = "magasin", "Boutique"
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
    class Paiement(models.TextChoices):
        ESPECES = "especes", "Espèces"
        CB = "cb", "Carte bancaire"
        MIXTE = "mixte", "Espèces + CB"

    # Mode de paiement des ventes en boutique (vide pour les ventes en ligne et les
    # ventes enregistrées avant la gestion de la caisse).
    paiement = models.CharField("paiement", max_length=10, choices=Paiement.choices, blank=True)
    montant_especes = models.DecimalField(
        "montant en espèces", max_digits=10, decimal_places=2, default=0,
        help_text="Part du total payée en espèces.",
    )
    # Ventes créées à partir d'une commande Shopify : commande et ligne d'origine.
    commande_shopify = models.ForeignKey(
        "CommandeShopify", on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes",
    )
    ligne_shopify = models.CharField(max_length=40, blank=True)
    # Compte qui a saisi la vente, pour la traçabilité. Une vente en ligne n'a pas de
    # vendeur (elle n'est attribuée à personne) mais garde la trace de qui l'a déclarée.
    saisie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ventes_saisies", verbose_name="saisie par",
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
    def montant_cb(self):
        if self.paiement in (self.Paiement.CB, self.Paiement.MIXTE):
            return self.chiffre_affaires - self.montant_especes
        return Decimal(0)

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


# Montant laissé dans la caisse après une récupération des espèces, proposé par défaut.
FOND_DE_CAISSE = Decimal("30.00")


class RecuperationEspeces(models.Model):
    """Un administrateur vide la caisse en y laissant un fond (30 € par défaut)."""

    date = models.DateTimeField(default=timezone.now, db_index=True)
    administrateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recuperations_especes"
    )
    especes_en_caisse = models.DecimalField(
        "espèces en caisse avant récupération", max_digits=10, decimal_places=2
    )
    fond_laisse = models.DecimalField("fond laissé dans la caisse", max_digits=10, decimal_places=2)
    montant_recupere = models.DecimalField("montant récupéré", max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["-date"]
        verbose_name = "récupération des espèces"
        verbose_name_plural = "récupérations des espèces"

    def __str__(self):
        return f"{self.montant_recupere} € le {timezone.localtime(self.date):%d/%m/%Y %H:%M}"


class CorrectionPaiement(models.Model):
    """Trace d'une correction du mode de paiement d'une vente par un administrateur."""

    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name="corrections_paiement")
    date = models.DateTimeField(default=timezone.now)
    administrateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ancien_paiement = models.CharField(max_length=10, choices=Vente.Paiement.choices, blank=True)
    ancien_montant_especes = models.DecimalField(max_digits=10, decimal_places=2)
    nouveau_paiement = models.CharField(max_length=10, choices=Vente.Paiement.choices)
    nouveau_montant_especes = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["-date"]
        verbose_name = "correction de paiement"
        verbose_name_plural = "corrections de paiement"


class CommandeShopify(models.Model):
    """Commande reçue de la boutique en ligne. Sert aussi à ne jamais l'enregistrer deux fois."""

    shopify_id = models.CharField(max_length=40, unique=True)
    nom = models.CharField("numéro", max_length=40)
    date = models.DateTimeField()
    annulee = models.BooleanField("annulée", default=False)
    recue_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "commande Shopify"
        verbose_name_plural = "commandes Shopify"

    def __str__(self):
        return self.nom


class EvenementShopify(models.Model):
    """Journal des échanges avec Shopify, consultable dans Administration → Shopify."""

    class Sens(models.TextChoices):
        ENVOI = "envoi", "Envoi vers Shopify"
        RECEPTION = "reception", "Reçu de Shopify"

    class Statut(models.TextChoices):
        OK = "ok", "OK"
        ERREUR = "erreur", "Erreur"
        IGNORE = "ignore", "Ignoré"

    date = models.DateTimeField(default=timezone.now, db_index=True)
    sens = models.CharField(max_length=10, choices=Sens.choices)
    action = models.CharField(max_length=60)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    message = models.TextField(blank=True)
    # Identifiant de notification Shopify : une notification reçue deux fois n'est traitée qu'une fois.
    webhook_id = models.CharField(max_length=80, blank=True, db_index=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "échange avec Shopify"
        verbose_name_plural = "échanges avec Shopify"
