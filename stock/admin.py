from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Ajustement, Reference, User, Vente


@admin.register(User)
class StockUserAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("Rôle dans l'application", {"fields": ["role"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {"fields": ["role"]}),)


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ["designation", "cout_achat", "prix_vente", "quantite", "active"]
    list_filter = ["active"]
    search_fields = ["designation"]
    # La quantité passe par les ventes et ajustements pour garder une trace.
    readonly_fields = ["quantite"]

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else []


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = [
        "date", "reference", "quantite", "prix_catalogue", "remise_pct", "prix_unitaire", "cout_unitaire", "canal", "vendeur"
    ]
    list_filter = ["canal", "remise_pct", "date"]
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
