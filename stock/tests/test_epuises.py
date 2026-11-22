from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import Ajustement, Categorie, Reference, User
from stock.tests.outils import vendre


class ArticlesEpuisesTests(TestCase):
    """Depuis 2.2.0 : plus d'onglet Rupture ; les articles épuisés s'affichent dans Stock sur demande."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        pull = Categorie.objects.get(nom="Pull")

        def ref(nom, quantite, **kw):
            return Reference.objects.create(designation=nom, categorie=pull, cout_achat=Decimal("10"),
                                            prix_vente=Decimal("30"), quantite=quantite, **kw)

        cls.vendu = ref("Pull vendu", 1)
        cls.jamais = ref("Pull jamais vendu", 0)
        cls.en_stock = ref("Pull en stock", 5)
        cls.masque = ref("Pull arrêté", 0, active=False)
        vendre(cls.vendu.pk, 1, cls.lea)  # dernière pièce vendue → épuisé

    def setUp(self):
        self.client.force_login(self.lea)

    def test_le_stock_ne_montre_que_les_articles_disponibles(self):
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, "Pull en stock")
        self.assertNotContains(r, "Pull vendu")
        self.assertNotContains(r, "Pull jamais vendu")
        self.assertContains(r, "Voir aussi les articles épuisés")

    def test_case_voir_aussi_les_epuises(self):
        r = self.client.get(reverse("stock_list") + "?epuises=1")
        self.assertEqual(sorted(x.designation for x in r.context["references"]),
                         ["Pull en stock", "Pull jamais vendu", "Pull vendu"])
        self.assertNotContains(r, "Pull arrêté")  # les articles masqués restent masqués
        # Un article épuisé ne se vend pas, mais s'ajuste (réassort exceptionnel).
        self.assertContains(r, reverse("ajuster", args=[self.vendu.pk]))
        self.assertEqual(r.context["pieces_en_stock"], 5)

    def test_plus_d_onglet_rupture(self):
        r = self.client.get(reverse("stock_list"))
        self.assertNotContains(r, ">Rupture")
        self.assertNotContains(r, 'class="compteur"')
        # Ancienne adresse (favoris) : le stock avec les épuisés.
        r = self.client.get("/ruptures/")
        self.assertRedirects(r, reverse("stock_list") + "?epuises=1")

    def test_retour_dans_le_stock_apres_reassort(self):
        services.ajuster_stock(self.vendu.pk, 3, Ajustement.Motif.REASSORT, self.admin)
        self.assertContains(self.client.get(reverse("stock_list")), "Pull vendu")

    def test_categorie_avant_designation_dans_ventes(self):
        html = self.client.get(reverse("ventes")).content.decode()
        self.assertLess(html.index("<th>Catégorie</th>"), html.index("<th>Désignation</th>"))
        self.assertIn('<td data-label="Catégorie">Pull</td>', html)
