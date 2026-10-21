import datetime
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import formats, timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import AjustementForm, ReferenceEditForm, ReferenceForm, VenteForm
from .models import Reference, User, Vente

MONEY = DecimalField(max_digits=14, decimal_places=2)
CA = ExpressionWrapper(F("prix_unitaire") * F("quantite"), output_field=MONEY)
REMISE = ExpressionWrapper((F("prix_catalogue") - F("prix_unitaire")) * F("quantite"), output_field=MONEY)
COUT = ExpressionWrapper(F("cout_unitaire") * F("quantite"), output_field=MONEY)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@login_required
def stock_list(request):
    q = request.GET.get("q", "").strip()
    refs = Reference.objects.filter(active=True)
    if q:
        refs = refs.filter(designation__icontains=q)
    return render(request, "stock/stock_list.html", {"references": refs, "q": q, "vente_form": VenteForm()})


@login_required
@require_POST
def vendre(request, pk):
    ref = get_object_or_404(Reference, pk=pk, active=True)
    form = VenteForm(request.POST)
    if form.is_valid():
        try:
            vente = services.enregistrer_vente(
                ref.pk,
                form.cleaned_data["quantite"],
                request.user,
                canal=form.cleaned_data["canal"],
                remise_pct=form.cleaned_data["remise_pct"],
            )
        except services.StockInsuffisant as e:
            messages.error(request, f"{ref} : {e}")
        else:
            prix = formats.number_format(vente.prix_unitaire, 2, use_l10n=True)
            solde = f" soldé −{vente.remise_pct} % à {prix} € pièce" if vente.remise_pct else ""
            canal = " en ligne" if vente.canal == Vente.Canal.EN_LIGNE else " en boutique"
            messages.success(request, f"Vente{canal} enregistrée : {vente.quantite} × {ref}{solde}.")
    else:
        messages.error(request, "Quantité ou solde invalide.")
    return redirect(request.POST.get("next") or "stock_list")


@login_required
def ajuster(request, pk):
    ref = get_object_or_404(Reference, pk=pk)
    form = AjustementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.ajuster_stock(
                ref.pk,
                form.cleaned_data["variation"],
                form.cleaned_data["motif"],
                request.user,
                form.cleaned_data["commentaire"],
            )
        except services.StockInsuffisant as e:
            form.add_error("variation", str(e))
        else:
            messages.success(request, f"Stock de « {ref} » ajusté.")
            return redirect("ajuster", pk=ref.pk)
    ref.refresh_from_db()
    return render(
        request,
        "stock/ajuster.html",
        {"ref": ref, "form": form, "ajustements": ref.ajustements.select_related("utilisateur")[:20]},
    )


@admin_required
def reference_create(request):
    form = ReferenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ref = form.save()
        messages.success(request, f"Référence « {ref} » créée.")
        return redirect("stock_list")
    return render(request, "stock/reference_form.html", {"form": form, "titre": "Nouvelle référence"})


@admin_required
def reference_edit(request, pk):
    ref = get_object_or_404(Reference, pk=pk)
    form = ReferenceEditForm(request.POST or None, instance=ref)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Référence « {ref} » modifiée.")
        return redirect("stock_list")
    return render(request, "stock/reference_form.html", {"form": form, "titre": f"Modifier « {ref} »", "ref": ref})


def _totaux(qs):
    t = qs.aggregate(ca=Sum(CA), cout=Sum(COUT), remises=Sum(REMISE), pieces=Sum("quantite"), nb=Count("id"))
    ca = t["ca"] or Decimal(0)
    return {
        "ca": ca,
        "pieces": t["pieces"] or 0,
        "nb": t["nb"],
        "remises": t["remises"] or Decimal(0),
        "marge": ca - (t["cout"] or Decimal(0)),
        "ca_boutique": qs.filter(canal=Vente.Canal.MAGASIN).aggregate(v=Sum(CA))["v"] or Decimal(0),
        "ca_en_ligne": qs.filter(canal=Vente.Canal.EN_LIGNE).aggregate(v=Sum(CA))["v"] or Decimal(0),
    }


@login_required
def ventes(request, mes_ventes=False, vendeuse=None, en_ligne=False):
    today = timezone.localdate()
    debut_mois = today.replace(day=1)
    qs = Vente.objects.select_related("reference", "vendeur")
    if mes_ventes:
        qs = qs.filter(vendeur=request.user)
        titre = "Mes ventes"
    elif vendeuse is not None:
        qs = qs.filter(vendeur=vendeuse)
        titre = f"Ventes de {vendeuse.get_short_name() or vendeuse.username}"
    elif en_ligne:
        qs = qs.filter(canal=Vente.Canal.EN_LIGNE)
        titre = "Ventes en ligne"
    else:
        titre = "Ventes"
    ventes_jour = qs.filter(date__date=today)
    ventes_mois = qs.filter(date__date__gte=debut_mois, date__date__lte=today)

    # Historique du mois (hors aujourd'hui), regroupé par jour avec un total par jour.
    jours = []
    for v in ventes_mois.filter(date__date__lt=today):
        jour = timezone.localtime(v.date).date()
        if not jours or jours[-1]["date"] != jour:
            jours.append({"date": jour, "ventes": [], "ca": Decimal(0), "pieces": 0})
        jours[-1]["ventes"].append(v)
        jours[-1]["ca"] += v.chiffre_affaires
        jours[-1]["pieces"] += v.quantite

    return render(
        request,
        "stock/ventes.html",
        {
            "ventes_jour": ventes_jour,
            "jour": _totaux(ventes_jour),
            "mois": _totaux(ventes_mois),
            "debut_mois": debut_mois,
            "jours": jours,
            "mes_ventes": mes_ventes,
            "vendeuse": vendeuse,
            "en_ligne": en_ligne,
            "toutes": not (mes_ventes or vendeuse or en_ligne),
            "titre": titre,
            # Boutons par vendeuse, réservés à l'administrateur.
            "vendeuses": (
                User.objects.filter(role=User.Role.RESTREINT, is_active=True).order_by("first_name", "username")
                if request.user.is_admin
                else []
            ),
        },
    )


@login_required
def mes_ventes(request):
    return ventes(request, mes_ventes=True)


@login_required
def ventes_en_ligne(request):
    return ventes(request, en_ligne=True)


@admin_required
def ventes_vendeuse(request, pk):
    vendeuse = get_object_or_404(User, pk=pk)
    return ventes(request, vendeuse=vendeuse)


@admin_required
@require_POST
def annuler_vente(request, pk):
    vente = get_object_or_404(Vente, pk=pk)
    services.annuler_vente(vente.pk)
    messages.success(request, f"Vente annulée, stock de « {vente.reference} » rétabli.")
    return redirect("ventes")


def _mois_courant(param):
    try:
        return datetime.datetime.strptime(param, "%Y-%m").date()
    except (TypeError, ValueError):
        return timezone.localdate().replace(day=1)


def _mois_suivant(d):
    return (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def _taux(marge, ca):
    return (marge / ca * 100) if ca else None


@admin_required
def marge(request):
    debut = _mois_courant(request.GET.get("mois"))
    fin = _mois_suivant(debut)
    tz = timezone.get_current_timezone()
    start = datetime.datetime.combine(debut, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(fin, datetime.time.min, tzinfo=tz)
    ventes_mois = Vente.objects.filter(date__gte=start, date__lt=end)

    totaux = ventes_mois.aggregate(
        ca=Sum(CA), cout=Sum(COUT), remises=Sum(REMISE), pieces=Sum("quantite"),
        pieces_soldees=Sum("quantite", filter=Q(remise_pct__gt=0)),
    )
    ca = totaux["ca"] or Decimal(0)
    cout = totaux["cout"] or Decimal(0)

    par_reference = (
        ventes_mois.values("reference__designation")
        .annotate(pieces=Sum("quantite"), ca=Sum(CA), cout=Sum(COUT))
        .annotate(marge=ExpressionWrapper(F("ca") - F("cout"), output_field=MONEY))
        .order_by("-marge")
    )
    for r in par_reference:
        r["taux"] = _taux(r["marge"], r["ca"])

    par_canal = []
    for valeur, libelle in Vente.Canal.choices:
        t = ventes_mois.filter(canal=valeur).aggregate(ca=Sum(CA), cout=Sum(COUT), pieces=Sum("quantite"))
        ca_canal = t["ca"] or Decimal(0)
        marge_canal = ca_canal - (t["cout"] or Decimal(0))
        par_canal.append(
            {"libelle": libelle, "pieces": t["pieces"] or 0, "ca": ca_canal, "marge": marge_canal,
             "taux": _taux(marge_canal, ca_canal)}
        )

    debut_historique = debut.replace(year=debut.year - 1)
    historique = (
        Vente.objects.filter(
            date__gte=datetime.datetime.combine(debut_historique, datetime.time.min, tzinfo=tz), date__lt=end
        )
        .annotate(mois=TruncMonth("date", tzinfo=tz))
        .values("mois")
        .annotate(ca=Sum(CA), cout=Sum(COUT))
        .annotate(marge=ExpressionWrapper(F("ca") - F("cout"), output_field=MONEY))
        .order_by("-mois")
    )
    for h in historique:
        h["taux"] = _taux(h["marge"], h["ca"])

    precedent = (debut - datetime.timedelta(days=1)).replace(day=1)
    return render(
        request,
        "stock/marge.html",
        {
            "debut": debut,
            "ca": ca,
            "cout": cout,
            "marge": ca - cout,
            "taux": _taux(ca - cout, ca),
            "pieces": totaux["pieces"] or 0,
            "remises": totaux["remises"] or Decimal(0),
            "pieces_soldees": totaux["pieces_soldees"] or 0,
            "par_reference": par_reference,
            "par_canal": par_canal,
            "historique": historique,
            "precedent": precedent.strftime("%Y-%m"),
            "suivant": fin.strftime("%Y-%m") if fin <= timezone.localdate() else None,
        },
    )
