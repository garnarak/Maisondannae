import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from stock import services
from stock.models import Ajustement, Categorie, Couleur, Modele, Reference, User
from stock.tests.outils import vendre


class VariantesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.robe = Categorie.objects.create(nom="Robe")
        cls.noir = Couleur.objects.get(nom="Noir")
        cls.ecru = Couleur.objects.get(nom="Écru")

    def _creer(self, **donnees):
        self.client.force_login(self.admin)
        base = {"categorie": self.robe.pk, "nom": "Robe portefeuille", "cout_achat": "25", "prix_vente": "69"}
        return self.client.post(reverse("modele_create"), {**base, **donnees}, follow=True)

    def test_creation_taille_par_couleur(self):
        r = self._creer(tailles=["L", "S", "M"], couleurs=[self.noir.pk, self.ecru.pk])
        self.assertContains(r, "créé avec 6 variante(s)")
        modele = Modele.objects.get()
        variantes = modele.variantes.all()
        self.assertEqual(len(variantes), 6)
        self.assertEqual({v.prix_vente for v in variantes}, {Decimal("69.00")})
        self.assertEqual({v.categorie for v in variantes}, {self.robe})
        self.assertIn("Robe portefeuille — M · Noir", {v.designation for v in variantes})
        self.assertEqual(len({v.sku for v in variantes}), 6)
        self.assertEqual(r.redirect_chain[-1][0], reverse("modele_edit", args=[modele.pk]))

    def test_taille_unique_sans_couleur(self):
        self._creer(tailles=["TU"])
        v = Reference.objects.get()
        self.assertEqual(v.designation, "Robe portefeuille")
        self.assertTrue(v.est_unique)

    def test_tailles_invalides(self):
        for tailles in ([], ["TU", "M"]):
            r = self._creer(tailles=tailles)
            self.assertEqual(r.status_code, 200)
            self.assertFalse(Modele.objects.exists())

    def test_entree_en_stock_et_prix_du_modele(self):
        self._creer(tailles=["S", "M"], couleurs=[self.noir.pk])
        modele = Modele.objects.get()
        s, m = sorted(modele.variantes.all(), key=lambda v: v.taille, reverse=True)  # S, M
        r = self.client.post(reverse("modele_edit", args=[modele.pk]),
                             {"action": "entree", f"q_{s.pk}": "3", f"q_{m.pk}": ""}, follow=True)
        self.assertContains(r, "3 pièce(s) entrée(s) en stock")
        s.refresh_from_db()
        self.assertEqual(s.quantite, 3)
        self.assertEqual(Ajustement.objects.get().motif, Ajustement.Motif.REASSORT)
        r = self.client.post(reverse("modele_edit", args=[modele.pk]), {"action": "entree", f"q_{m.pk}": "-2"},
                             follow=True)
        self.assertContains(r, "nombres entiers positifs")
        # Le prix se change une fois, sur le modèle, pour toutes les variantes.
        self.client.post(reverse("modele_edit", args=[modele.pk]), {
            "action": "modele", "categorie": self.robe.pk, "nom": "Robe cache-cœur", "cout_achat": "25",
            "prix_vente": "59", "active": "on"})
        self.assertEqual({(v.prix_vente, v.designation.split(" — ")[0]) for v in modele.variantes.all()},
                         {(Decimal("59.00"), "Robe cache-cœur")})

    def test_masquer_puis_reafficher_le_modele(self):
        self._creer(tailles=["S", "M"])
        modele = Modele.objects.get()
        modele.active = False
        modele.save()
        self.assertFalse(modele.variantes.filter(active=True).exists())
        modele.active = True
        modele.save()
        self.assertEqual(modele.variantes.filter(active=True).count(), 2)

    def test_ajouter_des_variantes(self):
        self._creer(tailles=["S", "M"])
        modele = Modele.objects.get()
        url = reverse("modele_edit", args=[modele.pk])
        self.client.post(url, {"action": "variantes", "tailles": ["XL"]})
        self.assertEqual(modele.variantes.count(), 3)
        # Seulement des couleurs : ajoutées à toutes les tailles existantes.
        self.client.post(url, {"action": "variantes", "couleurs": [self.noir.pk]})
        self.assertEqual(modele.variantes.filter(couleur=self.noir).count(), 3)
        r = self.client.post(url, {"action": "variantes", "tailles": ["S"]}, follow=True)
        self.assertContains(r, "existent déjà")

    def test_liste_du_stock_groupee_par_taille_et_vente_d_une_variante(self):
        self._creer(tailles=["L", "S", "M"], couleurs=[self.noir.pk])
        for v in Reference.objects.all():
            services.ajuster_stock(v.pk, 2, Ajustement.Motif.REASSORT, self.admin)
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertEqual([v.taille for v in r.context["references"]], ["S", "M", "L"])
        self.assertContains(r, '<span class="variante">M · Noir</span>', html=True)
        m = Reference.objects.get(taille="M")
        vendre(m.pk, 2, self.lea)
        r = self.client.get(reverse("ruptures"))
        self.assertContains(r, "Robe portefeuille — M · Noir")
        self.assertEqual(Reference.objects.get(taille="S").quantite, 2)


def classeur(lignes):
    wb = Workbook()
    ws = wb.active
    ws.append(["MODÈLE", "CATÉGORIE", "TAILLE", "COULEUR", "SKU", "COÛT D'ACHAT", "PRIX DE VENTE",
               "QUANTITÉ EN STOCK", "ACTIVE"])
    for l in lignes:
        ws.append(l)
    flux = io.BytesIO()
    wb.save(flux)
    flux.seek(0)
    flux.name = "stock.xlsx"
    return flux


class ImportVariantesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)

    def setUp(self):
        self.client.force_login(self.admin)

    def _importer(self, lignes):
        r = self.client.post(reverse("excel_import_stock"), {"fichier": classeur(lignes)})
        self.client.post(reverse("excel_import_stock"), {"confirmer": "1"})
        return r

    def test_import_de_variantes(self):
        r = self._importer([
            ["Jean flare", "Jean", "S", "Bleu", "", 20, 59, 2, "True"],
            ["Jean flare", "Jean", "M", "Bleu", "", 20, 59, 3, "True"],
            ["Jean flare", "Jean", "m", "Brut", "", 20, 59, 1, "True"],
            ["Foulard soie", "Accessoire", "", "", "FOU-01", 8, 25, 4, "True"],
        ])
        self.assertContains(r, "Nouvelles couleurs ajoutées à la liste : <strong>Brut</strong>")
        self.assertEqual(Modele.objects.count(), 2)
        self.assertEqual(Reference.objects.filter(modele__nom="Jean flare").count(), 3)
        self.assertEqual(Reference.objects.get(designation="Jean flare — M · Brut").quantite, 1)
        self.assertEqual(Reference.objects.get(sku="FOU-01").designation, "Foulard soie")
        self.assertTrue(Couleur.objects.filter(nom="Brut").exists())

    def test_mise_a_jour_par_sku_et_par_variante(self):
        self._importer([["Jean flare", "Jean", "S", "Bleu", "JF-S", 20, 59, 2, "True"]])
        r = self._importer([["Jean flare", "Jean", "S", "Bleu", "JF-S", 20, 65, 5, "True"]])
        self.assertContains(r, "stock 2 → 5")
        v = Reference.objects.get(sku="JF-S")
        self.assertEqual((v.quantite, v.prix_vente, Reference.objects.count()), (5, Decimal("65.00"), 1))

    def test_prix_differents_dans_un_meme_modele(self):
        r = self.client.post(reverse("excel_import_stock"), {"fichier": classeur([
            ["Jean flare", "Jean", "S", "Bleu", "", 20, 59, 2, "True"],
            ["Jean flare", "Jean", "M", "Bleu", "", 20, 69, 2, "True"],
        ])})
        self.assertContains(r, "doivent être identiques")
        self.assertContains(r, "Rien n'a été importé")

    def test_taille_inconnue(self):
        r = self.client.post(reverse("excel_import_stock"), {"fichier": classeur([
            ["Jean flare", "Jean", "38", "Bleu", "", 20, 59, 2, "True"]])})
        self.assertContains(r, "taille « 38 » inconnue")
