from django.test import TestCase
from django.urls import reverse

from stock.models import Categorie, Couleur, Modele, User


class CouleurDoubleTests(TestCase):
    """Cocher deux couleurs = une variante bicolore ; les couleurs doubles ne sont jamais
    proposées comme pastilles."""

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

    def test_deux_couleurs_cochees_une_variante_bicolore_par_taille(self):
        r = self.creer(couleurs=[self.blanc.pk, self.terra.pk])
        self.assertContains(r, "créé avec 2 variante(s)")
        v = Modele.objects.get().variantes.get(taille="M")
        self.assertEqual(v.couleur.nom, "Blanc / Terracotta")
        self.assertEqual(v.designation, "Robe rayée — M · Blanc / Terracotta")
        self.assertEqual(v.sku, f"MA{v.modele.pk:04d}-M-BLA-TER")
        # Recréée à l'identique pour un autre modèle, sans doublon dans les couleurs.
        self.creer(nom="Jupe rayée", couleurs=[self.blanc.pk, self.terra.pk])
        self.assertEqual(Couleur.objects.filter(nom="Blanc / Terracotta").count(), 1)

    def test_une_couleur_une_variante_unie(self):
        self.creer(couleurs=[self.noir.pk])
        self.assertEqual({v.couleur.nom for v in Modele.objects.get().variantes.all()}, {"Noir"})

    def test_ordre_de_selection_respecte(self):
        self.creer(couleurs=[self.blanc.pk, self.terra.pk], ordre_couleurs=f"{self.terra.pk},{self.blanc.pk}")
        self.assertTrue(Couleur.objects.filter(nom="Terracotta / Blanc").exists())

    def test_les_couleurs_doubles_ne_sont_pas_des_pastilles(self):
        Couleur.objects.create(nom="Taupe / Chocolat")
        r = self.client.get(reverse("modele_create"))
        self.assertNotContains(r, "Taupe / Chocolat")
        self.assertContains(r, "Blanc")

    def test_ajout_sur_la_page_du_modele(self):
        self.creer(couleurs=[self.noir.pk])
        modele = Modele.objects.get()
        r = self.client.post(reverse("modele_edit", args=[modele.pk]),
                             {"action": "variantes", "tailles": ["S", "M"], "couleurs": [self.blanc.pk, self.terra.pk]}, follow=True)
        self.assertContains(r, "2 variante(s) ajoutée(s)")
        self.assertEqual(modele.variantes.filter(couleur__nom="Blanc / Terracotta").count(), 2)
        # La variante bicolore existante est affichée dans le tableau du modèle.
        self.assertContains(r, "Blanc / Terracotta")

    def test_au_plus_deux_couleurs(self):
        r = self.creer(couleurs=[self.blanc.pk, self.terra.pk, self.noir.pk])
        self.assertContains(r, "Cochez au plus deux couleurs")
        self.assertFalse(Modele.objects.exists())

    def test_codes_proches_numerotes(self):
        a, _ = Couleur.objects.get_or_create(nom="Rouge bordeaux")
        b, _ = Couleur.objects.get_or_create(nom="Rouge bordelais")
        self.creer(tailles=["M"], couleurs=[a.pk])
        modele = Modele.objects.get()
        self.client.post(reverse("modele_edit", args=[modele.pk]), {"action": "variantes", "tailles": ["M"], "couleurs": [b.pk]})
        skus = list(modele.variantes.values_list("sku", flat=True))
        self.assertEqual(len(set(skus)), 2)


class TitresDesPages(TestCase):
    def test_pas_de_script_dans_le_titre(self):
        admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        self.client.force_login(admin)
        for nom in ("stock_list", "caisse"):
            html = self.client.get(reverse(nom)).content.decode()
            titre = html.split("<title>")[1].split("</title>")[0]
            self.assertNotIn("script", titre)
