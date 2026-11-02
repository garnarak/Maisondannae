from django.conf import settings


def app_version(request):
    return {"APP_VERSION": settings.APP_VERSION}


def ruptures(request):
    """Nombre d'articles en rupture, affiché dans le menu."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from .models import Reference

    return {"NB_RUPTURES": Reference.objects.filter(active=True, quantite=0).count()}
