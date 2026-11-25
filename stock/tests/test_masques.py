from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
import io

from stock import services
from stock.models import Ajustement, Categorie, Couleur, Modele, Reference, User
from stock.tests.outils import vendre


class ArticlesMasquesTests(TestCase):
    """2.2.1 : les anciens articles masqués à 0 n'encombrent plus, et reviennent d'eux-mêmes
    quand on les reçoit de nouveau, avec leur historique."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN, is_superuser=True)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.pull = Categorie.objects.get(nom="Pull")
        cls.noir, _ = Couleur.objects.get_or_create(nom="Noir")
        # Ancien article (avant le regroupement par couleurs), vendu puis masqué à 0.
        cls.ancien = services.creer_modele("Body dentelle chocolat", cls.pull, Decimal("8"), Decimal("25"), ["TU"], [])
        cls.ancienne_variante = cls.ancien.variantes.get()
        services.ajuster_stock(cls.ancienne_variante.pk, 1, Ajustement.Motif.REASSORT, cls.admin)
        cls.vente = vendre(cls.ancienne_variante.pk, 1, cls.lea)
        Reference.objects.filter(pk=cls.ancienne_variante.pk).update(active=False)
        # Article actuel, en stock.
        cls.actuel = services.creer_modele("Body dentelle", cls.pull, Decimal("8"), Decimal("25"), ["TU"], [cls.noir])
        services.ajuster_stock(cls.actuel.variantes.get().pk, 2, Ajustement.Motif.REASSORT, cls.admin)

    def setUp(self):
        self.client.force_login(self.admin)

    def lignes_export(self, **params):
        r = self.client.get(reverse("excel_export_stock"), params)
        ws = load_workbook(io.BytesIO(r.content)).active
        return [l[0] for l in ws.iter_rows(min_row=2, values_only=True) if l[0]]

    def test_export_sans_les_articles_masques(self):
        self.assertEqual(self.lignes_export(), ["Body dentelle"])
        self.assertEqual(sorted(self.lignes_export(masques="1")), ["Body dentelle", "Body dentelle chocolat"])

    def test_administration_affiche_seulement_les_articles_affiches(self):
        r = self.client.get(reverse("admin:stock_reference_changelist"))
        self.assertContains(r, "Body dentelle — Noir")
        self.assertNotContains(r, "Body dentelle chocolat")
        r = self.client.get(reverse("admin:stock_reference_changelist") + "?affichage=masques")
        self.assertContains(r, "Body dentelle chocolat")
        self.assertNotContains(r, "Body dentelle — Noir")
        r = self.client.get(reverse("admin:stock_modele_changelist"))
        self.assertNotContains(r, "Body dentelle chocolat")
        r = self.client.get(reverse("admin:stock_modele_changelist") + "?affichage=tous")
        self.assertContains(r, "Body dentelle chocolat")

    def test_l_historique_des_ventes_est_intact(self):
        r = self.client.get(reverse("ventes"))
        self.assertContains(r, "Body dentelle chocolat")

    def test_un_article_deja_eu_signale_a_la_creation(self):
        r = self.client.post(reverse("modele_create"), {
            "categorie": self.pull.pk, "nom": "body DENTELLE chocolat", "cout_achat": "8", "prix_vente": "25", "tailles": ["TU"],
        })
        self.assertContains(r, "Vous avez déjà eu cet article")
        self.assertContains(r, reverse("modele_edit", args=[self.ancien.pk]))
        self.assertEqual(Modele.objects.filter(nom__icontains="chocolat").count(), 1)

    def test_reprendre_cet_article(self):
        donnees = {"categorie": self.pull.pk, "nom": "Body DENTELLE chocolat", "cout_achat": "9.50", "prix_vente": "29",
                   "tailles": ["S", "M"], "couleurs": [self.noir.pk]}
        r = self.client.post(reverse("modele_create"), donnees)
        self.assertContains(r, "Reprendre cet article")
        r = self.client.post(reverse("modele_create"), {**donnees, "reprendre": str(self.ancien.pk)}, follow=True)
        self.assertRedirects(r, reverse("modele_edit", args=[self.ancien.pk]))
        self.assertContains(r, "repris, avec son historique")
        self.ancien.refresh_from_db()
        self.assertEqual((self.ancien.nom, self.ancien.cout_achat, self.ancien.prix_vente),
                         ("Body dentelle chocolat", Decimal("9.50"), Decimal("29.00")))
        self.assertEqual(Modele.objects.filter(nom__iexact="body dentelle chocolat").count(), 1)  # pas de doublon
        nouvelles = self.ancien.variantes.exclude(pk=self.ancienne_variante.pk)
        self.assertEqual(sorted(v.taille for v in nouvelles), ["M", "S"])
        self.assertEqual({v.prix_vente for v in self.ancien.variantes.all()}, {Decimal("29.00")})
        # La vente passée garde son prix et son coût d'origine.
        self.vente.refresh_from_db()
        self.assertEqual((self.vente.prix_unitaire, self.vente.cout_unitaire), (Decimal("25.00"), Decimal("8.00")))
        # L'article n'apparaît dans le stock qu'une fois les pièces reçues.
        self.assertNotContains(self.client.get(reverse("stock_list")), "Body dentelle chocolat")
        s = nouvelles.get(taille="S")
        self.client.post(reverse("modele_edit", args=[self.ancien.pk]), {"action": "entree", f"q_{s.pk}": "2"})
        self.assertContains(self.client.get(reverse("stock_list")), "Body dentelle chocolat")

    def test_reprendre_un_modele_masque_ne_reaffiche_pas_ses_anciennes_variantes(self):
        Modele.objects.filter(pk=self.ancien.pk).update(active=False)
        self.client.post(reverse("modele_create"), {
            "categorie": self.pull.pk, "nom": "Body dentelle chocolat", "cout_achat": "8", "prix_vente": "25",
            "tailles": ["M"], "reprendre": str(self.ancien.pk),
        })
        self.ancien.refresh_from_db()
        self.assertTrue(self.ancien.active)
        self.assertFalse(Reference.objects.get(pk=self.ancienne_variante.pk).active)

    def test_reprendre_refuse_si_le_formulaire_est_incomplet(self):
        r = self.client.post(reverse("modele_create"), {
            "categorie": self.pull.pk, "nom": "Body dentelle chocolat", "cout_achat": "8", "prix_vente": "25",
            "reprendre": str(self.ancien.pk),  # aucune taille cochée
        })
        self.assertContains(r, "Sélectionnez au moins une taille")
        self.assertEqual(self.ancien.variantes.count(), 1)

    def test_recevoir_des_pieces_reaffiche_l_article(self):
        r = self.client.get(reverse("modele_edit", args=[self.ancien.pk]))
        self.assertContains(r, "masqué")
        self.client.post(reverse("modele_edit", args=[self.ancien.pk]),
                         {"action": "entree", f"q_{self.ancienne_variante.pk}": "3"})
        v = Reference.objects.get(pk=self.ancienne_variante.pk)
        self.assertEqual((v.quantite, v.active), (3, True))
        self.assertContains(self.client.get(reverse("stock_list")), "Body dentelle chocolat")
        self.assertEqual(v.ventes.count(), 1)  # sa vente passée est toujours là

    def test_recherche_avec_epuises_retrouve_les_anciens_articles(self):
        self.client.force_login(self.lea)
        url = reverse("stock_list")
        self.assertNotContains(self.client.get(url, {"epuises": "1"}), "Body dentelle chocolat")
        self.assertNotContains(self.client.get(url, {"q": "chocolat"}), "Body dentelle chocolat")
        self.assertContains(self.client.get(url, {"q": "chocolat", "epuises": "1"}), "Body dentelle chocolat")

    def test_reimport_d_un_ancien_article_le_reaffiche(self):
        from stock import excel
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["MODÈLE", "CATÉGORIE", "TAILLE", "COULEUR", "SKU", "COÛT D'ACHAT", "PRIX DE VENTE", "QUANTITÉ EN STOCK", "ACTIVE"])
        ws.append(["Body dentelle chocolat", "Pull", "TU", None, None, 8, 25, 2, None])
        f = io.BytesIO()
        wb.save(f)
        analyse = excel.analyser_stock(io.BytesIO(f.getvalue()))
        self.assertFalse(analyse.erreurs)
        excel.importer_stock(analyse.lignes, self.admin)
        v = Reference.objects.get(pk=self.ancienne_variante.pk)
        self.assertEqual((v.quantite, v.active), (2, True))
