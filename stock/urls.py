from django.urls import path

from . import views

urlpatterns = [
    path("", views.stock_list, name="stock_list"),
    path("references/nouvelle/", views.reference_create, name="reference_create"),
    path("references/<int:pk>/modifier/", views.reference_edit, name="reference_edit"),
    path("references/<int:pk>/vendre/", views.vendre, name="vendre"),
    path("references/<int:pk>/ajuster/", views.ajuster, name="ajuster"),
    path("ventes/", views.ventes, name="ventes"),
    path("ventes/<int:pk>/annuler/", views.annuler_vente, name="annuler_vente"),
    path("marge/", views.marge, name="marge"),
]
