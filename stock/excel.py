"""Import et export Excel : stock (aller-retour au même format) et ventes."""

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import services
from .models import ORDRE_TAILLES, Ajustement, Categorie, Couleur, Modele, Reference, Taille, Vente

# Colonnes du fichier de stock, dans l'ordre de l'export : une ligne par variante. L'import
# les retrouve par leur titre (sans tenir compte des accents ni des majuscules), où qu'elles
# soient dans la feuille. « DÉSIGNATION » est accepté à la place de « MODÈLE » (anciens fichiers).
COLONNES_STOCK = ["MODÈLE", "CATÉGORIE", "TAILLE", "COULEUR", "SKU", "COÛT D'ACHAT", "PRIX DE VENTE",
                  "QUANTITÉ EN STOCK", "ACTIVE"]
OBLIGATOIRES = ["CATÉGORIE", "COÛT D'ACHAT", "PRIX DE VENTE", "QUANTITÉ EN STOCK"]
SANS_CATEGORIE = {"", "-", "—"}
SANS_COULEUR = {"", "-", "—"}
TAILLE_UNIQUE = {"", "TU", "TAILLE UNIQUE", "UNIQUE", "-"}


def _cle(texte):
    texte = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return " ".join(texte.replace("’", "'").upper().split())


def _montant(valeur):
    if valeur is None or str(valeur).strip() == "":
        raise ValueError("vide")
    try:
        montant = Decimal(str(valeur).strip().replace(",", ".").replace("€", "").replace(" ", ""))
    except InvalidOperation:
        raise ValueError(f"« {valeur} » n'est pas un nombre")
    if montant < 0:
        raise ValueError("négatif")
    return montant.quantize(Decimal("0.01"))


def _quantite(valeur):
    montant = _montant(valeur)
    if montant != montant.to_integral_value():
        raise ValueError(f"« {valeur} » n'est pas un nombre entier")
    return int(montant)


def _booleen(valeur):
    if valeur is None or str(valeur).strip() == "":
        return True
    return _cle(valeur) in {"TRUE", "VRAI", "OUI", "1", "X", "ACTIVE", "ACTIF"}


def _taille(valeur):
    cle = _cle(valeur)
    if cle in TAILLE_UNIQUE:
        return Taille.TU
    if cle in Taille.values:
        return cle
    raise ValueError(f"taille « {valeur} » inconnue (attendu : TU, XS, S, M, L, XL ou XXL)")


@dataclass
class LigneImport:
    numero: int
    modele: str
    categorie: str
    taille: str
    couleur: str
    sku: str
    cout_achat: Decimal
    prix_vente: Decimal
    quantite: int
    active: bool
    action: str = ""  # « création », « mise à jour » ou « inchangée »
    details: list = field(default_factory=list)

    @property
    def libelle(self):
        morceaux = [] if self.taille == Taille.TU else [self.taille]
        if self.couleur:
            morceaux.append(self.couleur)
        return f"{self.modele} — {' · '.join(morceaux)}" if morceaux else self.modele

    def vers_session(self):
        return {**self.__dict__, "cout_achat": str(self.cout_achat), "prix_vente": str(self.prix_vente)}

    @classmethod
    def depuis_session(cls, d):
        return cls(**{**d, "cout_achat": Decimal(d["cout_achat"]), "prix_vente": Decimal(d["prix_vente"])})


@dataclass
class AnalyseImport:
    lignes: list = field(default_factory=list)
    erreurs: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)
    nouvelles_categories: list = field(default_factory=list)
    nouvelles_couleurs: list = field(default_factory=list)


def _variante_existante(ligne, par_sku, par_cle):
    if ligne.sku and _cle(ligne.sku) in par_sku:
        return par_sku[_cle(ligne.sku)]
    return par_cle.get((_cle(ligne.modele), ligne.taille, _cle(ligne.couleur)))


def analyser_stock(fichier):
    """Lit le fichier et prépare l'import, sans rien enregistrer."""
    analyse = AnalyseImport()
    try:
        feuille = load_workbook(fichier, data_only=True, read_only=True).worksheets[0]
    except Exception:
        analyse.erreurs.append("Le fichier n'est pas un fichier Excel (.xlsx) lisible.")
        return analyse

    lignes = feuille.iter_rows(values_only=True)
    entetes = None
    for numero, ligne in enumerate(lignes, start=1):
        cles = [_cle(v) for v in ligne]
        if _cle("MODÈLE") in cles or _cle("DÉSIGNATION") in cles:
            entetes = {cle: index for index, cle in enumerate(cles) if cle}
            break
        if numero >= 10:
            break
    if entetes is None:
        analyse.erreurs.append("Ligne de titres introuvable : la feuille doit contenir une colonne « MODÈLE » "
                               "(ou « DÉSIGNATION »).")
        return analyse
    manquantes = [c for c in OBLIGATOIRES if _cle(c) not in entetes]
    if manquantes:
        analyse.erreurs.append("Colonnes manquantes : " + ", ".join(manquantes) + ".")
        return analyse
    colonne_modele = "MODÈLE" if _cle("MODÈLE") in entetes else "DÉSIGNATION"

    def cellule(ligne, colonne):
        index = entetes.get(_cle(colonne))
        return ligne[index] if index is not None and index < len(ligne) else None

    variantes = list(Reference.objects.select_related("modele", "couleur", "categorie"))
    par_sku = {_cle(v.sku): v for v in variantes if v.sku}
    par_cle = {(_cle(v.modele.nom), v.taille, _cle(v.couleur.nom if v.couleur else "")): v for v in variantes}
    categories = {_cle(c.nom): c.nom for c in Categorie.objects.all()}
    couleurs = {_cle(c.nom): c.nom for c in Couleur.objects.all()}
    vues, skus, modeles = set(), set(), {}
    for numero, ligne in enumerate(lignes, start=numero + 1):
        nom = str(cellule(ligne, colonne_modele) or "").strip()
        if not nom:
            continue  # ligne vide ou ligne de total
        try:
            cout = _montant(cellule(ligne, "COÛT D'ACHAT"))
            prix = _montant(cellule(ligne, "PRIX DE VENTE"))
            quantite = _quantite(cellule(ligne, "QUANTITÉ EN STOCK"))
            taille = _taille(cellule(ligne, "TAILLE"))
        except ValueError as e:
            analyse.erreurs.append(f"Ligne {numero} ({nom}) : valeur invalide — {e}.")
            continue

        couleur = str(cellule(ligne, "COULEUR") or "").strip()
        if couleur in SANS_COULEUR:
            couleur = ""
        elif _cle(couleur) in couleurs:
            couleur = couleurs[_cle(couleur)]
        elif couleur not in analyse.nouvelles_couleurs:
            analyse.nouvelles_couleurs.append(couleur)

        categorie = str(cellule(ligne, "CATÉGORIE") or "").strip()
        if categorie in SANS_CATEGORIE:
            categorie = ""
        elif _cle(categorie) in categories:
            categorie = categories[_cle(categorie)]
        elif categorie not in analyse.nouvelles_categories:
            analyse.nouvelles_categories.append(categorie)

        sku = str(cellule(ligne, "SKU") or "").strip()
        l = LigneImport(numero, nom, categorie, taille, couleur, sku, cout, prix, quantite,
                        _booleen(cellule(ligne, "ACTIVE")))

        cle = (_cle(nom), taille, _cle(couleur))
        if cle in vues:
            analyse.erreurs.append(f"Ligne {numero} : « {l.libelle} » apparaît plusieurs fois dans le fichier.")
            continue
        vues.add(cle)
        if sku:
            if _cle(sku) in skus:
                analyse.erreurs.append(f"Ligne {numero} : le SKU « {sku} » apparaît plusieurs fois dans le fichier.")
                continue
            skus.add(_cle(sku))
        # Prix, coût et catégorie appartiennent au modèle : toutes ses lignes doivent concorder.
        valeurs = (categorie, cout, prix)
        if _cle(nom) in modeles and modeles[_cle(nom)] != valeurs:
            analyse.erreurs.append(
                f"Ligne {numero} ({l.libelle}) : catégorie, coût ou prix différents des autres lignes du modèle "
                f"« {nom} ». Ils doivent être identiques pour toutes ses tailles et couleurs."
            )
            continue
        modeles.setdefault(_cle(nom), valeurs)
        if not categorie:
            analyse.avertissements.append(f"Ligne {numero} ({l.libelle}) : sans catégorie.")
        if prix < cout:
            analyse.avertissements.append(f"Ligne {numero} ({l.libelle}) : prix de vente inférieur au coût d'achat.")

        v = _variante_existante(l, par_sku, par_cle)
        if v is None:
            l.action = "création"
        else:
            l.modele = v.modele.nom
            changements = []
            if (v.categorie.nom if v.categorie else "") != categorie:
                changements.append(f"catégorie {v.categorie or '—'} → {categorie or '—'}")
            if v.cout_achat != cout:
                changements.append(f"coût {v.cout_achat} → {cout} €")
            if v.prix_vente != prix:
                changements.append(f"prix {v.prix_vente} → {prix} €")
            if v.quantite != quantite:
                changements.append(f"stock {v.quantite} → {quantite}")
            if v.active != l.active:
                changements.append("réactivée" if l.active else "masquée")
            if sku and v.sku != sku:
                changements.append(f"SKU {v.sku} → {sku}")
            l.action = "mise à jour" if changements else "inchangée"
            l.details = changements
        analyse.lignes.append(l)
    return analyse


@transaction.atomic
def importer_stock(lignes, utilisateur):
    """Enregistre les lignes analysées. Les quantités passent par un ajustement « Import Excel »
    pour garder la trace des mouvements de stock."""
    compte = {"création": 0, "mise à jour": 0, "inchangée": 0}
    categories, couleurs, modeles = {}, {}, {}
    variantes = list(Reference.objects.select_related("modele", "couleur"))
    par_sku = {_cle(v.sku): v for v in variantes if v.sku}
    par_cle = {(_cle(v.modele.nom), v.taille, _cle(v.couleur.nom if v.couleur else "")): v for v in variantes}
    for l in lignes:
        categorie = None
        if l.categorie:
            if l.categorie not in categories:
                categories[l.categorie], _ = Categorie.objects.get_or_create(nom=l.categorie)
            categorie = categories[l.categorie]
        couleur = None
        if l.couleur:
            if l.couleur not in couleurs:
                couleurs[l.couleur] = (Couleur.objects.filter(nom__iexact=l.couleur).first()
                                       or Couleur.objects.create(nom=l.couleur))
            couleur = couleurs[l.couleur]

        if _cle(l.modele) not in modeles:
            modele = Modele.objects.filter(nom__iexact=l.modele).first()
            if modele is None:
                modele = Modele.objects.create(nom=l.modele, categorie=categorie, cout_achat=l.cout_achat,
                                               prix_vente=l.prix_vente)
            else:
                modele.categorie, modele.cout_achat, modele.prix_vente = categorie, l.cout_achat, l.prix_vente
                modele.save()
            modeles[_cle(l.modele)] = modele
        modele = modeles[_cle(l.modele)]

        v = _variante_existante(l, par_sku, par_cle)
        if v is None:
            v = Reference.objects.create(modele=modele, taille=l.taille, couleur=couleur, sku=l.sku or None,
                                         quantite=0, active=l.active)
            ecart = l.quantite
        else:
            v.refresh_from_db()
            v.active = l.active
            if l.sku:
                v.sku = l.sku
            v.save()
            ecart = l.quantite - v.quantite
        if ecart:
            services.ajuster_stock(v.pk, ecart, Ajustement.Motif.INVENTAIRE, utilisateur, "Import Excel")
        compte[l.action] = compte.get(l.action, 0) + 1
    return compte


def _classeur(titre_feuille, colonnes, lignes, largeurs):
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = titre_feuille
    feuille.append(colonnes)
    for cellule in feuille[1]:
        cellule.font = Font(bold=True, color="FFFFFF")
        cellule.fill = PatternFill("solid", fgColor="C2185B")
    for ligne in lignes:
        feuille.append(ligne)
    for i, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(i)].width = largeur
    feuille.freeze_panes = "A2"
    feuille.auto_filter.ref = feuille.dimensions
    return classeur


def exporter_stock():
    variantes = sorted(
        Reference.objects.select_related("categorie", "couleur", "modele"),
        key=lambda v: (v.categorie.nom if v.categorie else "", v.modele.nom, ORDRE_TAILLES.get(v.taille, 99),
                       v.couleur.nom if v.couleur else ""),
    )
    lignes = [
        [v.modele.nom, v.categorie.nom if v.categorie else "", v.taille, v.couleur.nom if v.couleur else "",
         v.sku or "", float(v.cout_achat), float(v.prix_vente), v.quantite, "Oui" if v.active else "Non",
         float(v.cout_achat * v.quantite), float(v.prix_vente * v.quantite)]
        for v in variantes
    ]
    classeur = _classeur("Stock", COLONNES_STOCK + ["VALEUR D'ACHAT", "VALEUR DE VENTE"], lignes,
                         [36, 20, 9, 14, 18, 14, 14, 18, 10, 16, 16])
    feuille = classeur.active
    for colonne in "FGJK":
        for cellule in feuille[colonne][1:]:
            cellule.number_format = '#,##0.00 "€"'
    return classeur


def exporter_ventes(debut, fin):
    ventes = (
        Vente.objects.filter(date__date__gte=debut, date__date__lte=fin)
        .select_related("reference__categorie", "reference__couleur", "vendeur", "saisie_par").order_by("date")
    )
    lignes = []
    for v in ventes:
        moment = timezone.localtime(v.date)
        lignes.append([
            moment.date(), moment.strftime("%H:%M"), v.reference.designation, v.reference.taille,
            v.reference.couleur.nom if v.reference.couleur else "",
            v.reference.categorie.nom if v.reference.categorie else "", v.quantite,
            float(v.prix_catalogue), v.remise_pct or 0, float(v.prix_unitaire), float(v.chiffre_affaires),
            float(v.cout_unitaire * v.quantite), float(v.marge), v.get_canal_display(),
            v.get_paiement_display() if v.paiement else "", float(v.montant_especes), float(v.montant_cb),
            (v.vendeur.get_short_name() or v.vendeur.username) if v.vendeur else "",
            (v.saisie_par.get_short_name() or v.saisie_par.username) if v.saisie_par else "",
        ])
    colonnes = ["DATE", "HEURE", "RÉFÉRENCE", "TAILLE", "COULEUR", "CATÉGORIE", "QUANTITÉ", "PRIX INITIAL", "SOLDE (%)",
                "PRIX UNITAIRE", "TOTAL", "COÛT D'ACHAT", "MARGE", "CANAL", "PAIEMENT", "ESPÈCES", "CB",
                "VENDEUR", "SAISIE PAR"]
    classeur = _classeur("Ventes", colonnes, lignes, [12, 8, 40, 8, 12, 20, 10, 13, 10, 14, 12, 14, 12, 11, 15, 11, 11, 14, 14])
    feuille = classeur.active
    for cellule in feuille["A"][1:]:
        cellule.number_format = "DD/MM/YYYY"
    for colonne in "HJKLMPQ":
        for cellule in feuille[colonne][1:]:
            cellule.number_format = '#,##0.00 "€"'
    return classeur
