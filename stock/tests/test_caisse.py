from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import RecuperationEspeces, Reference, User, Vente


class PaiementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lea = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=10
        )

    def setUp(self):
        self.client.force_login(self.lea)

    def _payer(self, **donnees):
        return self.client.post(
            reverse("paiement", args=[self.robe.pk]), {"quantite": 2, **donnees}, follow=True
        )

    def test_ecran_de_paiement_affiche_le_total(self):
        r = self.client.get(reverse("paiement", args=[self.robe.pk]), {"quantite": 2, "remise_pct": 10})
        self.assertContains(r, "Total : <strong>90,00 €</strong>", html=True)

    def test_especes(self):
        r = self._payer(paiement="especes")
        self.assertContains(r, "Espèces")
        vente = Vente.objects.get()
        self.assertEqual(vente.paiement, Vente.Paiement.ESPECES)
        self.assertEqual(vente.montant_especes, Decimal("100.00"))

    def test_carte_bancaire(self):
        self._payer(paiement="cb")
        vente = Vente.objects.get()
        self.assertEqual(vente.montant_especes, Decimal("0"))
        self.assertEqual(vente.montant_cb, Decimal("100.00"))

    def test_especes_et_cb(self):
        self._payer(paiement="mixte", montant_especes="35,50".replace(",", "."))
        vente = Vente.objects.get()
        self.assertEqual(vente.paiement, Vente.Paiement.MIXTE)
        self.assertEqual(vente.montant_especes, Decimal("35.50"))
        self.assertEqual(vente.montant_cb, Decimal("64.50"))

    def test_mixte_refuse_un_montant_incoherent(self):
        for montant in ("", "0", "100", "150"):
            r = self._payer(paiement="mixte", montant_especes=montant)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "msg-error")
        self.assertFalse(Vente.objects.exists())
        self.robe.refresh_from_db()
        self.assertEqual(self.robe.quantite, 10)

    def test_mode_de_paiement_obligatoire(self):
        r = self._payer()
        self.assertContains(r, "Choisissez le mode de paiement")
        self.assertFalse(Vente.objects.exists())
        with self.assertRaises(services.PaiementInvalide):
            services.enregistrer_vente(self.robe.pk, 1, self.lea)

    def test_vente_en_ligne_sans_paiement_ni_especes(self):
        vente = services.enregistrer_vente(
            self.robe.pk, 1, self.lea, canal=Vente.Canal.EN_LIGNE, paiement="especes", montant_especes=Decimal("5")
        )
        self.assertEqual(vente.paiement, "")
        self.assertEqual(vente.montant_especes, Decimal("0"))


class CaisseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=20
        )

    def _vente(self, paiement, montant_especes=None, quantite=1):
        return services.enregistrer_vente(
            self.robe.pk, quantite, self.lea, paiement=paiement, montant_especes=montant_especes
        )

    def test_especes_en_caisse(self):
        self.assertEqual(services.especes_en_caisse(), Decimal("30.00"))  # fond de départ
        self._vente("especes")
        self._vente("cb")
        self._vente("mixte", Decimal("20"))
        services.enregistrer_vente(self.robe.pk, 1, self.lea, canal=Vente.Canal.EN_LIGNE)
        self.assertEqual(services.especes_en_caisse(), Decimal("100.00"))  # 30 + 50 + 20

    def test_recuperation_laisse_30_euros_par_defaut(self):
        self._vente("especes", quantite=3)  # 150 €
        self.client.force_login(self.admin)
        r = self.client.get(reverse("caisse"))
        self.assertEqual(r.context["en_caisse"], Decimal("180.00"))
        self.assertEqual(r.context["a_recuperer"], Decimal("150.00"))
        self.assertContains(r, 'value="30.00"')
        r = self.client.post(reverse("caisse"), {"fond_laisse": "30"}, follow=True)
        self.assertContains(r, "150,00 € récupérés, 30,00 € laissés")
        rec = RecuperationEspeces.objects.get()
        self.assertEqual((rec.especes_en_caisse, rec.montant_recupere, rec.fond_laisse, rec.administrateur),
                         (Decimal("180.00"), Decimal("150.00"), Decimal("30.00"), self.admin))
        self.assertEqual(services.especes_en_caisse(), Decimal("30.00"))
        self._vente("especes")
        self.assertEqual(services.especes_en_caisse(), Decimal("80.00"))

    def test_fond_modifiable(self):
        self._vente("especes", quantite=2)  # 100 €
        self.client.force_login(self.admin)
        self.client.post(reverse("caisse"), {"fond_laisse": "50.00"})
        self.assertEqual(RecuperationEspeces.objects.get().montant_recupere, Decimal("80.00"))
        self.assertEqual(services.especes_en_caisse(), Decimal("50.00"))

    def test_fond_impossible_refuse(self):
        self.client.force_login(self.admin)
        for fond in ("31", "-1"):
            r = self.client.post(reverse("caisse"), {"fond_laisse": fond})
            self.assertEqual(r.status_code, 200)
        self.assertFalse(RecuperationEspeces.objects.exists())

    def test_les_comptes_restreints_ne_recuperent_pas(self):
        self._vente("especes")
        self.client.force_login(self.lea)
        self.assertEqual(self.client.get(reverse("caisse")).status_code, 403)
        self.assertEqual(self.client.post(reverse("caisse"), {"fond_laisse": "30"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("stock_list")), reverse("caisse"))
        with self.assertRaises(PermissionError):
            services.recuperer_especes(self.lea)
        self.assertFalse(RecuperationEspeces.objects.exists())

    def test_suivi_mensuel(self):
        self._vente("especes", quantite=2)  # 100 € espèces
        self._vente("cb")  # 50 € CB
        self._vente("mixte", Decimal("10"))  # 10 € espèces + 40 € CB
        services.recuperer_especes(self.admin)  # 30 + 110 − 30 = 110 €
        self.client.force_login(self.admin)
        mois = self.client.get(reverse("caisse")).context["suivi"][0]
        self.assertEqual(mois["especes"], Decimal("110.00"))
        self.assertEqual(mois["cb"], Decimal("90.00"))
        self.assertEqual(mois["recupere"], Decimal("110.00"))
