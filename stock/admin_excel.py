"""Pages « Import / export Excel » de l'administration."""

import datetime
from functools import wraps

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from . import excel
from .models import Ajustement

SESSION_IMPORT = "import_stock_en_attente"
# Motifs proposés pour les pièces ajoutées par un import (arrivage ou recomptage).
MOTIFS_HAUSSES = [Ajustement.Motif.REASSORT, Ajustement.Motif.INVENTAIRE]


def reserve_aux_administrateurs(vue):
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return vue(request, *args, **kwargs)

    return admin.site.admin_view(enveloppe)


def _telechargement(classeur, nom):
    reponse = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    classeur.save(reponse)
    return reponse


def _contexte(request, **extra):
    return {**admin.site.each_context(request), "title": "Import / export Excel", **extra}


@reserve_aux_administrateurs
def accueil(request):
    aujourd_hui = timezone.localdate()
    return render(request, "admin/excel/accueil.html", _contexte(
        request, debut=aujourd_hui.replace(day=1).isoformat(), fin=aujourd_hui.isoformat(),
    ))


@reserve_aux_administrateurs
def export_stock(request):
    avec_masques = request.GET.get("masques") == "1"
    return _telechargement(excel.exporter_stock(avec_masques), f"stock-{timezone.localdate():%Y-%m-%d}.xlsx")


@reserve_aux_administrateurs
def export_ventes(request):
    try:
        debut = datetime.date.fromisoformat(request.GET.get("debut", ""))
        fin = datetime.date.fromisoformat(request.GET.get("fin", ""))
    except ValueError:
        messages.error(request, "Choisissez une date de début et une date de fin valides.")
        return redirect("excel_accueil")
    if fin < debut:
        debut, fin = fin, debut
    return _telechargement(excel.exporter_ventes(debut, fin), f"ventes-{debut:%Y-%m-%d}-au-{fin:%Y-%m-%d}.xlsx")


@reserve_aux_administrateurs
def import_stock(request):
    if request.method == "POST" and "confirmer" in request.POST:
        lignes = [excel.LigneImport.depuis_session(d) for d in request.session.pop(SESSION_IMPORT, [])]
        if not lignes:
            messages.error(request, "Aucun import en attente : déposez à nouveau le fichier.")
            return redirect("excel_accueil")
        motif = request.POST.get("motif_hausses")
        if motif not in MOTIFS_HAUSSES:
            motif = Ajustement.Motif.INVENTAIRE
        compte = excel.importer_stock(lignes, request.user, motif)
        messages.success(
            request,
            f"Import terminé : {compte['création']} référence(s) créée(s), {compte['mise à jour']} mise(s) à jour, "
            f"{compte['inchangée']} inchangée(s).",
        )
        return redirect("excel_accueil")

    if request.method == "POST" and request.FILES.get("fichier"):
        analyse = excel.analyser_stock(request.FILES["fichier"])
        if analyse.erreurs:
            request.session.pop(SESSION_IMPORT, None)
        else:
            request.session[SESSION_IMPORT] = [l.vers_session() for l in analyse.lignes]
        return render(request, "admin/excel/apercu.html", _contexte(
            request, analyse=analyse, nom_fichier=request.FILES["fichier"].name,
            creations=[l for l in analyse.lignes if l.action == "création"],
            mises_a_jour=[l for l in analyse.lignes if l.action == "mise à jour"],
            inchangees=[l for l in analyse.lignes if l.action == "inchangée"],
            pieces=sum(l.quantite for l in analyse.lignes),
            ajoutees=sum(l.ecart for l in analyse.lignes if l.ecart > 0),
            retirees=-sum(l.ecart for l in analyse.lignes if l.ecart < 0),
            motifs=[(m, Ajustement.Motif(m).label) for m in MOTIFS_HAUSSES],
        ))
    messages.error(request, "Choisissez un fichier Excel à importer.")
    return redirect("excel_accueil")
