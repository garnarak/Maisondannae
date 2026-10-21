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


class VentesEnLigneNonAttribueesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x", first_name="Léa")
        cls.robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30.00"), prix_vente=Decimal("50.00"), quantite=10
        )
        cls.pull = Reference.objects.create(
            designation="Pull angora", cout_achat=Decimal("20.00"), prix_vente=Decimal("80.00"), quantite=10
        )

    def setUp(self):
        services.enregistrer_vente(self.robe.pk, 1, self.lea)  # boutique
        services.enregistrer_vente(self.pull.pk, 2, self.lea, canal=Vente.Canal.EN_LIGNE)

    def test_la_vente_en_ligne_n_a_pas_de_vendeur_mais_garde_la_saisie(self):
        en_ligne = Vente.objects.get(canal=Vente.Canal.EN_LIGNE)
        self.assertIsNone(en_ligne.vendeur)
        self.assertEqual(en_ligne.saisie_par, self.lea)
        boutique = Vente.objects.get(canal=Vente.Canal.MAGASIN)
        self.assertEqual(boutique.vendeur, self.lea)
        self.assertEqual(boutique.saisie_par, self.lea)

    def test_mes_ventes_exclut_les_ventes_en_ligne(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("mes_ventes"))
        self.assertEqual(r.context["mois"]["ca"], Decimal("50.00"))
        self.assertNotContains(r, "Pull angora")

    def test_les_chiffres_d_une_vendeuse_excluent_les_ventes_en_ligne(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("ventes_vendeuse", args=[self.lea.pk]))
        self.assertEqual(r.context["mois"]["ca"], Decimal("50.00"))

    def test_bouton_et_page_ventes_en_ligne_pour_tous(self):
        for compte in (self.lea, self.admin):
            self.client.force_login(compte)
            r = self.client.get(reverse("ventes"))
            self.assertContains(r, reverse("ventes_en_ligne"))
            r = self.client.get(reverse("ventes_en_ligne"))
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "<h1>Ventes en ligne</h1>", html=True)
            self.assertEqual(r.context["jour"]["ca"], Decimal("160.00"))
            self.assertEqual(r.context["mois"]["ca"], Decimal("160.00"))
            self.assertContains(r, "Pull angora")
            self.assertNotContains(r, "Robe lin")

    def test_ordre_des_boutons(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("ventes")).content.decode()
        self.assertLess(html.index("Mes ventes</a>"), html.index("Léa</a>"))
        self.assertLess(html.index("Léa</a>"), html.index("Ventes en ligne</a>"))
        self.client.force_login(self.lea)
        html = self.client.get(reverse("ventes")).content.decode()
        self.assertLess(html.index("Mes ventes</a>"), html.index("Ventes en ligne</a>"))

    def test_toutes_les_ventes_inclut_les_deux_canaux(self):
        self.client.force_login(self.lea)
        r = self.client.get(reverse("ventes"))
        self.assertEqual(r.context["mois"]["ca"], Decimal("210.00"))
