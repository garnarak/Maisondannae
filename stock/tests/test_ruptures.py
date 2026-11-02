from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import Ajustement, Categorie, Reference, User
from stock.tests.outils import vendre


class RupturesTests(TestCase):
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
        vendre(cls.vendu.pk, 1, cls.lea)  # dernière pièce vendue → rupture

    def test_les_ruptures_quittent_l_onglet_stock(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, "Pull en stock")
        self.assertNotContains(r, "Pull vendu")
        self.assertNotContains(r, "Pull jamais vendu")

    def test_onglet_rupture(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("ruptures"))
        self.assertEqual([x.designation for x in r.context["ruptures"]], ["Pull jamais vendu", "Pull vendu"])
        self.assertNotContains(r, "Pull en stock")
        self.assertNotContains(r, "Pull arrêté")
        self.assertContains(r, reverse("ajuster", args=[self.vendu.pk]))
        self.assertIsNotNone(r.context["ruptures"][1].derniere_vente)

    def test_retour_dans_le_stock_apres_reassort(self):
        services.ajuster_stock(self.vendu.pk, 3, Ajustement.Motif.REASSORT, self.admin)
        self.client.force_login(self.lea)
        self.assertContains(self.client.get(reverse("stock_list")), "Pull vendu")
        self.assertNotContains(self.client.get(reverse("ruptures")), "Pull vendu")

    def test_compteur_dans_le_menu(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, 'Rupture <span class="compteur">2</span>', html=True)

    def test_cout_reserve_aux_administrateurs(self):
        self.client.force_login(self.lea)
        self.assertNotContains(self.client.get(reverse("ruptures")), "Coût d'achat")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("ruptures")), "Coût d'achat")

    def test_connexion_obligatoire(self):
        self.assertEqual(self.client.get(reverse("ruptures")).status_code, 302)
