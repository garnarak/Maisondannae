"""Écran « Arrivage » : tout un réassort saisi dans un seul tableau, puis enregistré d'un coup.

Une ligne = un article dans une taille et une couleur, avec le nombre de pièces reçues.
Les lignes passent par la même vérification que l'import Excel, puis par le même
enregistrement (motif « Réassort »), avec trois facilités :
- un nom vide reprend l'article de la ligne du dessus (autre couleur ou taille du même article) ;
- catégorie, coût ou prix vides reprennent ceux déjà saisis pour l'article, sinon ceux de
  l'article déjà connu de l'outil (article déjà eu, repris avec son historique) ;
- une même taille × couleur saisie deux fois est additionnée.
"""

from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from . import excel
from .models import Ajustement, Categorie, Couleur, Modele, Reference, Taille
from .views import admin_required

SESSION = "arrivage_en_attente"
CHAMPS = ["nom", "categorie", "taille", "couleur", "quantite", "cout", "prix"]


def _vide(ligne):
    # La taille a toujours une valeur (TU par défaut) : elle ne compte pas pour dire si la ligne est remplie.
    return not any(v for c, v in ligne.items() if c != "taille")


LIGNES_AU_DEPART = 20


def _couleur(texte, connues):
    """« blanc/terracotta » → « Blanc / Terracotta » : chaque couleur prend l'écriture de la liste
    des couleurs, sinon une majuscule ; deux couleurs sont séparées par « / » comme ailleurs."""
    parties = [" ".join(p.split()) for p in str(texte or "").split("/")]
    parties = [connues.get(excel._cle(p)) or (p[:1].upper() + p[1:]) for p in parties if p]
    return " / ".join(parties)


def lignes_saisies(post):
    """Lignes du tableau envoyé : listes de valeurs, une par champ, dans l'ordre des lignes."""
    colonnes = [post.getlist(c) for c in CHAMPS]
    n = max((len(c) for c in colonnes), default=0)
    return [{c: (colonnes[i][k].strip() if k < len(colonnes[i]) else "") for i, c in enumerate(CHAMPS)}
            for k in range(n)]


def preparer(saisie):
    """Transforme le tableau en lignes de stock (quantité totale après arrivage) et vérifie le tout.
    Renvoie (analyse, recapitulatif)."""
    analyse = excel.AnalyseImport()
    modeles = {excel._cle(m.nom): m for m in Modele.objects.select_related("categorie")}
    couleurs = {excel._cle(c.nom): c.nom for c in Couleur.objects.all()}
    variantes = {(excel._cle(v.modele.nom), v.taille, excel._cle(v.couleur.nom if v.couleur else "")): v
                 for v in Reference.objects.select_related("modele", "couleur") if v.modele_id}
    # 1re passe : article de chaque ligne (vide = celui du dessus) et valeurs saisies par article.
    remplies, precedent, saisies = [], "", {}
    for numero, l in enumerate(saisie, start=1):
        if _vide(l):
            continue
        nom = " ".join(l["nom"].split()) or precedent
        if not nom:
            analyse.erreurs.append(f"Ligne {numero} : indiquez l'article.")
            continue
        precedent = nom
        connues = saisies.setdefault(excel._cle(nom), ["", "", ""])
        for i, valeur in enumerate((l["categorie"], l["cout"], l["prix"])):
            if valeur and not connues[i]:
                connues[i] = valeur
        remplies.append((numero, nom, l))

    # 2e passe : valeurs manquantes complétées (tableau, sinon article déjà connu), doublons additionnés.
    fusion = {}  # (article, taille, couleur) → ligne à importer
    for numero, nom, l in remplies:
        cle_modele = excel._cle(nom)
        existant = modeles.get(cle_modele)
        defaut = [existant.categorie.nom if existant and existant.categorie else "",
                  str(existant.cout_achat) if existant else "", str(existant.prix_vente) if existant else ""]
        categorie, cout, prix = (v or saisies[cle_modele][i] or defaut[i]
                                 for i, v in enumerate((l["categorie"], l["cout"], l["prix"])))
        if not cout or not prix:
            analyse.erreurs.append(f"Ligne {numero} ({nom}) : indiquez le coût d'achat et le prix de vente.")
            continue
        if not l["quantite"]:
            analyse.erreurs.append(f"Ligne {numero} ({nom}) : indiquez le nombre de pièces reçues.")
            continue
        try:
            recu = excel._quantite(l["quantite"])
            taille = excel._taille(l["taille"])
        except ValueError as e:
            analyse.erreurs.append(f"Ligne {numero} ({nom}) : quantité ou taille invalide — {e}.")
            continue
        if recu <= 0:
            analyse.erreurs.append(f"Ligne {numero} ({nom}) : indiquez le nombre de pièces reçues.")
            continue
        couleur = _couleur(l["couleur"], couleurs)
        cle = (cle_modele, taille, excel._cle(couleur))
        if cle in fusion:
            fusion[cle]["recu"] += recu
            continue
        fusion[cle] = {"numero": numero, "nom": existant.nom if existant else nom, "taille": taille,
                       "couleur": couleur, "recu": recu, "valeurs": (categorie, cout, prix),
                       "avant": variantes[cle].quantite if cle in variantes else 0}

    entetes = {excel._cle(c): i for i, c in enumerate(excel.COLONNES_STOCK)}
    lignes = []
    for f in fusion.values():
        categorie, cout, prix = f["valeurs"]
        lignes.append((f["numero"], (f["nom"], categorie, f["taille"], f["couleur"], None, cout, prix,
                                     f["avant"] + f["recu"], "Oui")))
    if analyse.erreurs:
        return analyse, None
    analyse = excel.analyser_lignes(entetes, lignes, analyse)
    if analyse.erreurs:
        return analyse, None
    recus = {f["numero"]: f["recu"] for f in fusion.values()}
    recap = {
        "articles": len({excel._cle(l.modele) for l in analyse.lignes}),
        "nouveaux": len({excel._cle(l.modele) for l in analyse.lignes if excel._cle(l.modele) not in modeles}),
        "repris": len({excel._cle(l.modele) for l in analyse.lignes if excel._cle(l.modele) in modeles}),
        "pieces": sum(recus.values()),
        "valeur": sum((l.cout_achat * recus[l.numero] for l in analyse.lignes), Decimal(0)),
        "lignes": [(l, recus[l.numero]) for l in analyse.lignes],
    }
    return analyse, recap


def _contexte(saisie, **extra):
    while saisie and _vide(saisie[-1]):
        saisie.pop()
    while len(saisie) < LIGNES_AU_DEPART or not _vide(saisie[-1]):
        saisie.append({c: "" for c in CHAMPS})
    articles = {
        m.nom: [m.categorie.nom if m.categorie else "", str(m.cout_achat), str(m.prix_vente)]
        for m in Modele.objects.select_related("categorie")
    }
    return {
        "saisie": saisie,
        "articles": articles,
        "categories": Categorie.objects.all(),
        "couleurs": Couleur.objects.exclude(nom__contains="/"),
        "tailles": Taille.values,
        **extra,
    }


@admin_required
def arrivage(request):
    if request.method == "POST" and "confirmer" in request.POST:
        en_attente = request.session.pop(SESSION, None)
        if not en_attente:
            messages.error(request, "Aucun arrivage en attente : vérifiez à nouveau le tableau.")
            return redirect("arrivage")
        lignes = [excel.LigneImport.depuis_session(d) for d in en_attente["lignes"]]
        excel.importer_stock(lignes, request.user, Ajustement.Motif.REASSORT)
        messages.success(
            request, f"Arrivage enregistré : {en_attente['pieces']} pièce(s), {en_attente['articles']} article(s). "
                     "Ils sont dans le stock.",
        )
        return redirect(reverse("stock_list"))

    if request.method == "POST":
        saisie = lignes_saisies(request.POST)
        analyse, recap = preparer(saisie)
        if recap:
            request.session[SESSION] = {"lignes": [l.vers_session() for l in analyse.lignes],
                                        "pieces": recap["pieces"], "articles": recap["articles"]}
        else:
            request.session.pop(SESSION, None)
        return render(request, "stock/arrivage.html", _contexte(saisie, analyse=analyse, recap=recap))

    return render(request, "stock/arrivage.html", _contexte([]))
