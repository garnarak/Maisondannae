from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from stock import pwa

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manifest.webmanifest", pwa.manifeste, name="manifeste"),
    path("sw.js", pwa.service_worker, name="service_worker"),
    path("hors-ligne/", pwa.hors_ligne, name="hors_ligne"),
    path("connexion/", auth_views.LoginView.as_view(), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("stock.urls")),
]
