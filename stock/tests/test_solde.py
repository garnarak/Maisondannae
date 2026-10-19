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


class ChiffreAffairesDuJourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.vendeuse = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("89.99"), quantite=10
        )

    def test_total_du_jour(self):
        import datetime

        from django.utils import timezone

        services.enregistrer_vente(self.robe.pk, 2, self.vendeuse, remise_pct=30)  # 2 × 62,99
        services.enregistrer_vente(self.robe.pk, 1, self.vendeuse)  # 89,99
        Vente.objects.create(  # hier : ne compte pas
            reference=self.robe, quantite=1, prix_unitaire=Decimal("89.99"), cout_unitaire=Decimal("30"),
            date=timezone.now() - datetime.timedelta(days=1),
        )
        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["jour"]["ca"], Decimal("215.97"))
        self.assertEqual(r.context["jour"]["pieces"], 3)
        self.assertEqual(r.context["jour"]["nb"], 2)
        self.assertContains(r, "215,97 €")
        self.assertNotContains(r, "Marge du jour")

        self.client.force_login(self.admin)
        r = self.client.get(reverse("ventes"))
        self.assertContains(r, "Marge du jour")
        self.assertEqual(r.context["jour"]["marge"], Decimal("125.97"))

    def test_journee_sans_vente(self):
        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["jour"]["ca"], Decimal("0"))
        self.assertContains(r, "0,00 €")


class HistoriqueDuMoisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendeuse = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=10
        )

    def _vente_le(self, jour, quantite=1):
        import datetime

        from django.utils import timezone

        moment = timezone.make_aware(datetime.datetime.combine(jour, datetime.time(15, 0)))
        return Vente.objects.create(
            reference=self.robe, quantite=quantite, prix_unitaire=Decimal("50.00"),
            cout_unitaire=Decimal("30.00"), date=moment, vendeur=self.vendeuse,
        )

    def test_la_vendeuse_voit_le_mois_en_cours(self):
        import datetime

        from django.utils import timezone

        today = timezone.localdate()
        debut = today.replace(day=1)
        services.enregistrer_vente(self.robe.pk, 1, self.vendeuse)  # aujourd'hui
        if today.day > 1:
            self._vente_le(debut, quantite=2)  # plus tôt ce mois-ci
        self._vente_le(debut - datetime.timedelta(days=1))  # mois précédent : exclu

        self.client.force_login(self.vendeuse)
        r = self.client.get(reverse("ventes"))
        attendu = 3 if today.day > 1 else 1
        self.assertEqual(r.context["mois"]["pieces"], attendu)
        self.assertEqual(r.context["mois"]["ca"], Decimal("50.00") * attendu)
        self.assertContains(r, "Chiffre d'affaires du mois")
        self.assertNotContains(r, "Marge du mois")
        jours = r.context["jours"]
        if today.day > 1:
            # Aujourd'hui n'est pas répété dans l'historique.
            self.assertEqual([j["date"] for j in jours], [debut])
            self.assertEqual(jours[0]["ca"], Decimal("100.00"))
        else:
            self.assertEqual(jours, [])


class ChiffresParVendeurTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.sarah = User.objects.create_user("sarah", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=10
        )
        cls.pull = Reference.objects.create(
            designation="Pull angora", cout_achat=Decimal("20.00"), prix_vente=Decimal("80.00"), quantite=10
        )

    def test_chaque_vendeuse_ne_voit_que_ses_chiffres(self):
        services.enregistrer_vente(self.robe.pk, 1, self.lea)
        services.enregistrer_vente(self.pull.pk, 2, self.sarah)

        self.client.force_login(self.lea)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["jour"]["ca"], Decimal("50.00"))
        self.assertEqual(r.context["mois"]["ca"], Decimal("50.00"))
        self.assertContains(r, "Robe lin")
        self.assertNotContains(r, "Pull angora")
        self.assertContains(r, "Mes ventes aujourd")

        self.client.force_login(self.sarah)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["jour"]["ca"], Decimal("160.00"))
        self.assertNotContains(r, "Robe lin")

    def test_l_administrateur_voit_toute_la_boutique(self):
        services.enregistrer_vente(self.robe.pk, 1, self.lea)
        services.enregistrer_vente(self.pull.pk, 2, self.sarah)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["jour"]["ca"], Decimal("210.00"))
        self.assertContains(r, "Robe lin")
        self.assertContains(r, "Pull angora")
