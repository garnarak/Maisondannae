from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import Reference, User, Vente, prix_remise


class SoldeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.vendeuse = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("89.99"), quantite=10
        )

    def test_calcul_et_arrondi(self):
        self.assertEqual(prix_remise(Decimal("89.99"), 30), Decimal("62.99"))  # 62,993
        self.assertEqual(prix_remise(Decimal("89.99"), 50), Decimal("45.00"))  # 44,995 arrondi au-dessus
        self.assertEqual(prix_remise(Decimal("89.99"), 0), Decimal("89.99"))

    def test_vente_soldee_depuis_la_tablette(self):
        self.client.force_login(self.vendeuse)
        r = self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 2, "remise_pct": 30}, follow=True)
        self.assertContains(r, "soldé −30 % à 62,99 € pièce")
        vente = Vente.objects.get()
        self.assertEqual(vente.prix_catalogue, Decimal("89.99"))
        self.assertEqual(vente.remise_pct, 30)
        self.assertEqual(vente.prix_unitaire, Decimal("62.99"))
        self.assertEqual(vente.marge, Decimal("65.98"))
        self.assertEqual(vente.montant_remise, Decimal("54.00"))
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 8)
        self.assertEqual(self.robe.prix_vente, Decimal("89.99"))  # le prix de la référence ne change pas

    def test_sans_solde_par_defaut(self):
        self.client.force_login(self.vendeuse)
        self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 1})
        vente = Vente.objects.get()
        self.assertEqual(vente.remise_pct, 0)
        self.assertEqual(vente.prix_unitaire, Decimal("89.99"))

    def test_pourcentage_non_autorise_refuse(self):
        self.client.force_login(self.vendeuse)
        r = self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 1, "remise_pct": 90}, follow=True)
        self.assertContains(r, "Quantité ou solde invalide")
        self.assertFalse(Vente.objects.exists())
        with self.assertRaises(ValueError):
            services.enregistrer_vente(self.robe.pk, 1, self.admin, remise_pct=15)

    def test_liste_propose_les_prix_soldes(self):
        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, "Prix normal")
        self.assertContains(r, "−70 % · 27,00 €")

    def test_historique_et_synthese(self):
        services.enregistrer_vente(self.robe.pk, 2, self.vendeuse, remise_pct=30)
        services.enregistrer_vente(self.robe.pk, 1, self.vendeuse)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("ventes")), "−30 %")
        r = self.client.get(reverse("marge"))
        self.assertEqual(r.context["ca"], Decimal("215.97"))
        self.assertEqual(r.context["remises"], Decimal("54.00"))
        self.assertEqual(r.context["pieces_soldees"], 2)
