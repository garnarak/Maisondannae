from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from stock import admin_excel, pwa

urlpatterns = [
    path("admin/excel/", admin_excel.accueil, name="excel_accueil"),
    path("admin/excel/export-stock/", admin_excel.export_stock, name="excel_export_stock"),
    path("admin/excel/export-ventes/", admin_excel.export_ventes, name="excel_export_ventes"),
    path("admin/excel/import-stock/", admin_excel.import_stock, name="excel_import_stock"),
    path("admin/", admin.site.urls),
    path("manifest.webmanifest", pwa.manifeste, name="manifeste"),
    path("sw.js", pwa.service_worker, name="service_worker"),
    path("hors-ligne/", pwa.hors_ligne, name="hors_ligne"),
    path("connexion/", auth_views.LoginView.as_view(), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("stock.urls")),
]
