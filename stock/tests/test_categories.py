from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock.models import Categorie, Reference, User


class CategoriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("garnik", "", "x")
        cls.lea = User.objects.create_user("lea", password="x")
        cls.pull = Categorie.objects.get(nom="Pull")
        cls.jean = Categorie.objects.get(nom="Jean")

    def test_categories_de_depart(self):
        self.assertEqual(
            sorted(Categorie.objects.values_list("nom", flat=True)),
            sorted(["Veste", "Pantalon", "Jean", "Chemise", "Pull", "Débardeur", "T-shirt manche longue"]),
        )

    def test_categorie_obligatoire_a_la_creation(self):
        self.client.force_login(self.admin)
        donnees = {"designation": "Pull col roulé", "cout_achat": "20", "prix_vente": "50", "quantite": "3",
                   "active": "on"}
        r = self.client.post(reverse("reference_create"), donnees)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Reference.objects.exists())
        self.assertContains(r, "Choisir une catégorie")
        self.client.post(reverse("reference_create"), {**donnees, "categorie": self.pull.pk})
        self.assertEqual(Reference.objects.get().categorie, self.pull)

    def test_modifier_la_categorie(self):
        ref = Reference.objects.create(designation="Slim brut", categorie=self.pull, cout_achat=Decimal("20"),
                                       prix_vente=Decimal("60"), quantite=2)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reference_edit", args=[ref.pk]))
        self.assertContains(r, 'name="categorie"')
        self.client.post(reverse("reference_edit", args=[ref.pk]), {
            "designation": "Slim brut", "categorie": self.jean.pk, "cout_achat": "20", "prix_vente": "60",
            "active": "on",
        })
        ref.refresh_from_db()
        self.assertEqual(ref.categorie, self.jean)

    def test_colonne_et_filtre_dans_le_stock(self):
        Reference.objects.create(designation="Pull angora", categorie=self.pull, cout_achat=1, prix_vente=2, quantite=1)
        Reference.objects.create(designation="Jean droit", categorie=self.jean, cout_achat=1, prix_vente=2, quantite=1)
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, "Désignation · Catégorie")
        self.assertContains(r, '<span class="categorie">Pull</span>', html=True)
        self.assertContains(r, "Pull angora")
        self.assertContains(r, "Jean droit")
        r = self.client.get(reverse("stock_list"), {"categorie": self.jean.pk})
        self.assertContains(r, "Jean droit")
        self.assertNotContains(r, "Pull angora")

    def test_ajout_de_categorie_depuis_l_administration(self):
        self.client.force_login(self.admin)
        r = self.client.post("/admin/stock/categorie/add/", {"nom": "Robe"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Categorie.objects.filter(nom="Robe").exists())
        # Les vendeuses n'ont pas accès à l'administration.
        self.client.force_login(self.lea)
        self.client.post("/admin/stock/categorie/add/", {"nom": "Short"})
        self.assertFalse(Categorie.objects.filter(nom="Short").exists())

    def test_confirmation_avant_vente_en_ligne(self):
        Reference.objects.create(designation="Pull angora", categorie=self.pull, cout_achat=1, prix_vente=2, quantite=1)
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, 'onclick="return confirmerVenteEnLigne(this)"')
        self.assertContains(r, "Déclarer une vente EN LIGNE")
