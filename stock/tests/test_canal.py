from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import Reference, User, Vente


class VentesEnLigneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=10
        )

    def test_la_vendeuse_declare_une_vente_en_ligne(self):
        self.client.force_login(self.lea)
        r = self.client.post(
            reverse("vendre", args=[self.robe.pk]), {"quantite": 2, "canal": "en_ligne"}, follow=True
        )
        self.assertContains(r, "Vente en ligne enregistrée : 2 × Robe lin")
        vente = Vente.objects.get()
        self.assertEqual(vente.canal, Vente.Canal.EN_LIGNE)
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 8)  # le stock est partagé entre les deux canaux

    def test_par_defaut_la_vente_est_en_boutique(self):
        self.client.force_login(self.lea)
        r = self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 1}, follow=True)
        self.assertContains(r, "Vente en boutique enregistrée")
        self.assertEqual(Vente.objects.get().canal, Vente.Canal.MAGASIN)

    def test_canal_inconnu_refuse(self):
        self.client.force_login(self.lea)
        self.client.post(reverse("vendre", args=[self.robe.pk]), {"quantite": 1, "canal": "marche"})
        self.assertFalse(Vente.objects.exists())

    def test_les_deux_boutons_sont_proposes(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, 'name="canal" value="magasin"')
        self.assertContains(r, 'name="canal" value="en_ligne"')

    def test_repartition_boutique_en_ligne(self):
        services.enregistrer_vente(self.robe.pk, 1, self.lea)
        services.enregistrer_vente(self.robe.pk, 2, self.lea, canal=Vente.Canal.EN_LIGNE)
        self.client.force_login(self.lea)
        r = self.client.get(reverse("ventes"))
        for periode in ("jour", "mois"):
            self.assertEqual(r.context[periode]["ca"], Decimal("150.00"))
            self.assertEqual(r.context[periode]["ca_boutique"], Decimal("50.00"))
            self.assertEqual(r.context[periode]["ca_en_ligne"], Decimal("100.00"))
        self.assertContains(r, '<span class="badge canal">En ligne</span>')

        self.client.force_login(self.admin)
        r = self.client.get(reverse("marge"))
        canaux = {c["libelle"]: c for c in r.context["par_canal"]}
        self.assertEqual(canaux["Boutique"]["ca"], Decimal("50.00"))
        self.assertEqual(canaux["En ligne"]["ca"], Decimal("100.00"))
        self.assertEqual(canaux["En ligne"]["marge"], Decimal("40.00"))
