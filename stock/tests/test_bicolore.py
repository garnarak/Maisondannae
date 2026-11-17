from django.test import TestCase
from django.urls import reverse

from stock.models import Categorie, Couleur, Modele, User


class CouleurDoubleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.robe = Categorie.objects.create(nom="Robe")
        cls.blanc, _ = Couleur.objects.get_or_create(nom="Blanc")
        cls.terra, _ = Couleur.objects.get_or_create(nom="Terracotta")
        cls.noir, _ = Couleur.objects.get_or_create(nom="Noir")

    def setUp(self):
        self.client.force_login(self.admin)

    def creer(self, **donnees):
        base = {"categorie": self.robe.pk, "nom": "Robe rayée", "cout_achat": "25", "prix_vente": "69", "tailles": ["S", "M"]}
        return self.client.post(reverse("modele_create"), {**base, **donnees}, follow=True)

    def test_deux_couleurs_cochees_sans_couleur_double_donnent_deux_variantes_par_taille(self):
        r = self.creer(couleurs=[self.blanc.pk, self.terra.pk])
        self.assertContains(r, "créé avec 4 variante(s)")
        self.assertFalse(Couleur.objects.filter(nom__contains=" / ").exists())

    def test_couleur_double(self):
        r = self.creer(couleurs=[self.blanc.pk, self.terra.pk], couleur_double="on")
        self.assertContains(r, "créé avec 2 variante(s)")
        v = Modele.objects.get().variantes.get(taille="M")
        self.assertEqual(v.couleur.nom, "Blanc / Terracotta")
        self.assertEqual(v.designation, "Robe rayée — M · Blanc / Terracotta")
        self.assertEqual(v.sku, f"MA{v.modele.pk:04d}-M-BLA-TER")
        # La couleur double rejoint la liste et se réutilise ensuite, sans doublon.
        self.creer(nom="Jupe rayée", couleurs=[self.blanc.pk, self.terra.pk], couleur_double="on")
        self.assertEqual(Couleur.objects.filter(nom="Blanc / Terracotta").count(), 1)

    def test_ordre_de_selection_respecte(self):
        ordre = f"{self.terra.pk},{self.blanc.pk}"
        self.creer(couleurs=[self.blanc.pk, self.terra.pk], couleur_double="on", ordre_couleurs=ordre)
        self.assertTrue(Couleur.objects.filter(nom="Terracotta / Blanc").exists())

    def test_ajout_sur_la_page_du_modele(self):
        self.creer(couleurs=[self.noir.pk])
        modele = Modele.objects.get()
        r = self.client.post(reverse("modele_edit", args=[modele.pk]), {
            "action": "variantes", "couleurs": [self.blanc.pk, self.terra.pk], "couleur_double": "on",
        }, follow=True)
        self.assertContains(r, "2 variante(s) ajoutée(s)")
        self.assertEqual(modele.variantes.filter(couleur__nom="Blanc / Terracotta").count(), 2)

    def test_il_faut_exactement_deux_couleurs_simples(self):
        r = self.creer(couleurs=[self.blanc.pk], couleur_double="on")
        self.assertContains(r, "cochez exactement deux couleurs")
        r = self.creer(couleurs=[self.blanc.pk, self.terra.pk, self.noir.pk], couleur_double="on")
        self.assertContains(r, "cochez exactement deux couleurs")
        double = Couleur.objects.create(nom="Blanc / Noir")
        r = self.creer(couleurs=[double.pk, self.terra.pk], couleur_double="on")
        self.assertContains(r, "deux couleurs simples")
        self.assertFalse(Modele.objects.exists())

    def test_codes_proches_numerotes(self):
        a, _ = Couleur.objects.get_or_create(nom="Rouge bordeaux")
        b, _ = Couleur.objects.get_or_create(nom="Rouge bordelais")
        self.creer(tailles=["M"], couleurs=[a.pk, b.pk])
        skus = sorted(Modele.objects.get().variantes.values_list("sku", flat=True))
        self.assertEqual(len(set(skus)), 2)


class TitresDesPages(TestCase):
    def test_pas_de_script_dans_le_titre(self):
        admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        self.client.force_login(admin)
        for nom in ("stock_list", "caisse"):
            html = self.client.get(reverse(nom)).content.decode()
            titre = html.split("<title>")[1].split("</title>")[0]
            self.assertNotIn("script", titre)
