from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Ajustement, Categorie, Couleur, Modele, RecuperationEspeces, Reference, User, Vente


@admin.register(User)
class StockUserAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("Rôle dans l'application", {"fields": ["role"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {"fields": ["role"]}),)


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ["nom", "nombre_de_references"]
    search_fields = ["nom"]

    @admin.display(description="références")
    def nombre_de_references(self, obj):
        return obj.references.count()


@admin.register(Couleur)
class CouleurAdmin(admin.ModelAdmin):
    list_display = ["nom", "nombre_de_variantes"]
    search_fields = ["nom"]

    @admin.display(description="variantes")
    def nombre_de_variantes(self, obj):
        return obj.variantes.count()


class VarianteInline(admin.TabularInline):
    model = Reference
    fields = ["taille", "couleur", "sku", "quantite", "active"]
    readonly_fields = ["taille", "couleur", "quantite"]
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False  # les variantes s'ajoutent depuis la page du modèle dans l'outil


@admin.register(Modele)
class ModeleAdmin(admin.ModelAdmin):
    list_display = ["nom", "categorie", "cout_achat", "prix_vente", "nombre_de_variantes", "active"]
    list_filter = ["active", "categorie"]
    search_fields = ["nom"]
    inlines = [VarianteInline]

    @admin.display(description="variantes")
    def nombre_de_variantes(self, obj):
        return obj.variantes.count()

    def has_add_permission(self, request):
        return False  # création dans l'outil : Stock → « Nouveau modèle »


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ["designation", "categorie", "taille", "couleur", "sku", "prix_vente", "quantite", "active"]
    list_filter = ["active", "categorie", "taille", "couleur"]
    search_fields = ["designation", "sku"]
    fields = ["modele", "taille", "couleur", "sku", "quantite", "active"]
    # Le modèle porte nom, prix et coût ; la quantité passe par les ventes et ajustements.
    readonly_fields = ["modele", "taille", "couleur", "quantite"]

    def has_add_permission(self, request):
        return False


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = [
        "date", "reference", "quantite", "prix_catalogue", "remise_pct", "prix_unitaire", "cout_unitaire", "canal", "paiement", "montant_especes", "vendeur", "saisie_par"
    ]
    list_filter = ["canal", "paiement", "remise_pct", "date"]
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ajustement)
class AjustementAdmin(admin.ModelAdmin):
    list_display = ["date", "reference", "variation", "motif", "utilisateur"]
    list_filter = ["motif"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecuperationEspeces)
class RecuperationEspecesAdmin(admin.ModelAdmin):
    list_display = ["date", "administrateur", "especes_en_caisse", "montant_recupere", "fond_laisse"]
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
