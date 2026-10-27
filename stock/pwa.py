"""Application installable (PWA) : manifeste, service worker et page hors connexion."""

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

COULEUR_THEME = "#c2185b"
COULEUR_FOND = "#fff9f4"


@cache_control(max_age=3600)
def manifeste(request):
    icones = [
        {"src": static("img/icones/icone-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": static("img/icones/icone-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": static("img/icones/icone-maskable-192.png"), "sizes": "192x192", "type": "image/png",
         "purpose": "maskable"},
        {"src": static("img/icones/icone-maskable-512.png"), "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ]
    donnees = {
        "id": "/",
        "name": "Maison d'Annaé — Stock",
        "short_name": "Maison d'Annaé",
        "description": "Gestion du stock, des ventes et de la caisse de la boutique.",
        "lang": "fr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": COULEUR_THEME,
        "background_color": COULEUR_FOND,
        "icons": icones,
    }
    return JsonResponse(donnees, content_type="application/manifest+json", json_dumps_params={"ensure_ascii": False})


# Le service worker ne met en cache que la page hors connexion : les pages de l'outil
# (stock, ventes, caisse) sont toujours chargées depuis le serveur, pour ne jamais
# afficher des chiffres périmés.
SERVICE_WORKER = """
const CACHE = "maisondannae-{version}";
const HORS_LIGNE = "/hors-ligne/";

self.addEventListener("install", (event) => {{
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(HORS_LIGNE)));
  self.skipWaiting();
}});

self.addEventListener("activate", (event) => {{
  event.waitUntil(
    caches.keys().then((noms) => Promise.all(noms.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
  );
  self.clients.claim();
}});

self.addEventListener("fetch", (event) => {{
  if (event.request.mode === "navigate") {{
    event.respondWith(fetch(event.request).catch(() => caches.match(HORS_LIGNE)));
  }}
}});
"""


@cache_control(no_cache=True)
def service_worker(request):
    reponse = HttpResponse(SERVICE_WORKER.format(version=settings.APP_VERSION), content_type="application/javascript")
    reponse["Service-Worker-Allowed"] = "/"
    return reponse


def hors_ligne(request):
    return render(request, "hors_ligne.html", {"couleur": COULEUR_THEME, "fond": COULEUR_FOND})
