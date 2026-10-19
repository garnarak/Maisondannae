import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stock import services
from stock.models import Ajustement, Reference, User, Vente


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.vendeuse = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("31.17"), prix_vente=Decimal("89.00"), quantite=5
        )


class DroitsTests(BaseTestCase):
    def test_anonyme_redirige_vers_connexion(self):
        r = self.client.get(reverse("stock_list"))
        self.assertRedirects(r, f"{reverse('login')}?next=/")

    def test_restreint_ne_voit_pas_le_cout(self):
        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, "89,00")
        self.assertNotContains(r, "31,17")
        self.assertNotContains(r, "Coût")

    def test_admin_voit_le_cout(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("stock_list")), "31,17")

    def test_restreint_ne_peut_pas_modifier_prix_ni_voir_marge(self):
        self.client.force_login(self.vendeuse)
        for url in [reverse("reference_edit", args=[self.robe.pk]), reverse("reference_create"), reverse("marge")]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        r = self.client.post(
            reverse("reference_edit", args=[self.robe.pk]),
            {"designation": "Robe lin", "cout_achat": "1", "prix_vente": "1", "active": "on"},
        )
        self.assertEqual(r.status_code, 403)
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.prix_vente, Decimal("89.00"))

    def test_restreint_ne_voit_pas_la_marge_des_ventes(self):
        services.enregistrer_vente(self.robe.pk, 1, self.admin)
        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("ventes"))
        self.assertContains(r, "Robe lin")
        self.assertNotContains(r, "57,83")  # marge unitaire
        self.assertNotContains(r, "Annuler")

    def test_restreint_n_a_pas_acces_a_l_admin_django(self):
        self.assertFalse(self.vendeuse.is_staff)
        self.assertTrue(self.admin.is_staff)

    def test_restreint_peut_vendre_et_ajuster(self):
        self.client.force_login(self.vendeuse)
        self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 2})
        self.client.post(reverse("ajuster", args=[self.robe.pk]), {"variation": 4, "motif": "reassort"})
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 7)


class VenteTests(BaseTestCase):
    def test_vente_decremente_le_stock_et_fige_prix_et_cout(self):
        vente = services.enregistrer_vente(self.robe.pk, 2, self.vendeuse)
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 3)
        Reference.objects.filter(pk=self.robe.pk).update(prix_vente=99, cout_achat=40)
        vente.refresh_from_db()
        self.assertEqual(vente.prix_unitaire, Decimal("89.00"))
        self.assertEqual(vente.cout_unitaire, Decimal("31.17"))
        self.assertEqual(vente.marge, Decimal("115.66"))

    def test_stock_insuffisant(self):
        with self.assertRaises(services.StockInsuffisant):
            services.enregistrer_vente(self.robe.pk, 6, self.vendeuse)
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 5)
        self.assertFalse(Vente.objects.exists())

    def test_annulation_remet_en_stock(self):
        vente = services.enregistrer_vente(self.robe.pk, 2, self.vendeuse)
        self.client.force_login(self.admin)
        self.client.post(reverse("annuler_vente", args=[vente.pk]))
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 5)
        self.assertFalse(Vente.objects.exists())

    def test_ajustement_ne_rend_pas_le_stock_negatif(self):
        with self.assertRaises(services.StockInsuffisant):
            services.ajuster_stock(self.robe.pk, -6, Ajustement.Motif.CASSE, self.admin)
        services.ajuster_stock(self.robe.pk, -5, Ajustement.Motif.CASSE, self.admin)
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 0)


class MargeTests(BaseTestCase):
    def test_synthese_mensuelle(self):
        pull = Reference.objects.create(designation="Pull", cout_achat=10, prix_vente=20, quantite=10)
        services.enregistrer_vente(self.robe.pk, 2, self.vendeuse)  # marge 115,66
        services.enregistrer_vente(pull.pk, 3, self.vendeuse)  # marge 30
        # Une vente du mois précédent ne doit pas compter.
        Vente.objects.create(
            reference=pull, quantite=1, prix_unitaire=20, cout_unitaire=10,
            date=timezone.now() - datetime.timedelta(days=40),
        )
        self.client.force_login(self.admin)
        r = self.client.get(reverse("marge"))
        self.assertEqual(r.context["ca"], Decimal("238.00"))
        self.assertEqual(r.context["marge"], Decimal("145.66"))
        lignes = list(r.context["par_reference"])
        self.assertEqual([l["reference__designation"] for l in lignes], ["Robe lin", "Pull"])
        self.assertEqual(len(r.context["historique"]), 2)
