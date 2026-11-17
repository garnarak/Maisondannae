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

    def test_creation_avec_une_couleur_double(self):
        r = self.creer(couleurs=[self.noir.pk], bicolore_1=self.blanc.pk, bicolore_2=self.terra.pk)
        self.assertContains(r, "créé avec 4 variante(s)")
        v = Modele.objects.get().variantes.get(taille="M", couleur__nom="Blanc / Terracotta")
        self.assertEqual(v.designation, "Robe rayée — M · Blanc / Terracotta")
        self.assertEqual(v.sku, f"MA{v.modele.pk:04d}-M-BLA-TER")
        # La couleur double rejoint la liste et se réutilise ensuite.
        self.assertTrue(Couleur.objects.filter(nom="Blanc / Terracotta").exists())
        self.creer(nom="Jupe rayée", bicolore_1=self.blanc.pk, bicolore_2=self.terra.pk)
        self.assertEqual(Couleur.objects.filter(nom="Blanc / Terracotta").count(), 1)

    def test_ajout_sur_la_page_du_modele(self):
        self.creer(couleurs=[self.noir.pk])
        modele = Modele.objects.get()
        r = self.client.post(reverse("modele_edit", args=[modele.pk]),
                             {"action": "variantes", "bicolore_1": self.blanc.pk, "bicolore_2": self.terra.pk}, follow=True)
        self.assertContains(r, "2 variante(s) ajoutée(s)")
        self.assertContains(r, "Blanc / Terracotta")

    def test_une_seule_couleur_ou_deux_fois_la_meme(self):
        r = self.creer(bicolore_1=self.blanc.pk)
        self.assertContains(r, "choisissez les deux couleurs")
        r = self.creer(bicolore_1=self.blanc.pk, bicolore_2=self.blanc.pk)
        self.assertContains(r, "deux couleurs différentes")
        self.assertFalse(Modele.objects.exists())

    def test_codes_proches_numerotes(self):
        a, _ = Couleur.objects.get_or_create(nom="Rouge bordeaux")
        b, _ = Couleur.objects.get_or_create(nom="Rouge bordelais")
        self.creer(tailles=["M"], couleurs=[a.pk, b.pk])
        skus = sorted(Modele.objects.get().variantes.values_list("sku", flat=True))
        self.assertEqual(len(set(skus)), 2)

    def test_les_couleurs_doubles_ne_sont_pas_proposees_comme_couleur_1(self):
        Couleur.objects.create(nom="Blanc / Noir")
        r = self.client.get(reverse("modele_create"))
        champ = r.context["variantes_form"].fields["bicolore_1"]
        self.assertNotIn("Blanc / Noir", [c.nom for c in champ.queryset])
