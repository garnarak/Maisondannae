"""Page « Shopify » de l'administration et adresse de réception des notifications Shopify."""

import json

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import shopify
from .admin_excel import reserve_aux_administrateurs
from .models import CommandeShopify, EvenementShopify, Reference


@reserve_aux_administrateurs
def accueil(request):
    variantes = Reference.objects.all()
    return render(request, "admin/shopify/accueil.html", {
        **admin.site.each_context(request),
        "title": "Shopify",
        "actif": shopify.ClientShopify.actif(),
        "boutique": settings.SHOPIFY_SHOP,
        "signature": bool(settings.SHOPIFY_WEBHOOK_SECRET),
        "adresse_notifications": request.build_absolute_uri(reverse("shopify_notifications")),
        "nb_variantes": variantes.count(),
        "nb_liees": variantes.exclude(shopify_inventory_item_id="").count(),
        "nb_a_synchroniser": variantes.filter(shopify_a_synchroniser=True).count(),
        "nb_commandes": CommandeShopify.objects.count(),
        "evenements": EvenementShopify.objects.all()[:50],
    })


ACTIONS = {
    "tester": "Tester la connexion",
    "resynchroniser": "Tout renvoyer à Shopify",
    "creer": "Créer les produits manquants",
    "abonner": "Recevoir les commandes",
}


@require_POST
@reserve_aux_administrateurs
def action(request, nom):
    if not shopify.ClientShopify.actif():
        messages.error(request, "Le couplage Shopify n'est pas configuré (voir les étapes ci-dessous).")
        return redirect("shopify_accueil")
    try:
        if nom == "tester":
            boutique, emplacements = shopify.tester_connexion()
            messages.success(request, f"Connexion réussie à « {boutique} ». Emplacement(s) de stock : {', '.join(emplacements) or 'aucun'}.")
        elif nom == "resynchroniser":
            shopify.resynchroniser_tout()
            messages.success(request, "Stock et prix renvoyés à Shopify. Le détail est dans le journal ci-dessous.")
        elif nom == "creer":
            n = shopify.creer_produits_manquants()
            messages.success(request, f"{n} produit(s) créé(s) dans Shopify, en brouillon : vérifiez-les puis publiez-les depuis Shopify."
                             if n else "Aucun produit à créer : tous les modèles existent déjà dans Shopify.")
        elif nom == "abonner":
            n = shopify.abonner_notifications(request.build_absolute_uri(reverse("shopify_notifications")))
            messages.success(request, f"Shopify préviendra désormais l'outil des commandes ({n} abonnement(s) ajouté(s)).")
        else:
            return HttpResponseBadRequest()
    except shopify.ErreurShopify as e:
        shopify.journaliser(EvenementShopify.Sens.ENVOI, ACTIONS.get(nom, nom), EvenementShopify.Statut.ERREUR, str(e))
        messages.error(request, str(e))
    return redirect("shopify_accueil")


@csrf_exempt
@require_POST
def notifications(request):
    """Adresse appelée par Shopify. Seules les notifications signées avec le secret de
    l'application sont acceptées."""
    corps = request.body
    if not shopify.signature_valide(corps, request.headers.get("X-Shopify-Hmac-Sha256", "")):
        return HttpResponse("Signature invalide", status=401)
    try:
        donnees = json.loads(corps)
    except ValueError:
        return HttpResponseBadRequest()
    shopify.recevoir_notification(
        request.headers.get("X-Shopify-Topic", ""), request.headers.get("X-Shopify-Webhook-Id", ""), donnees,
    )
    return HttpResponse("OK")
