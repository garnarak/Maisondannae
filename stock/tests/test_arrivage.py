from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stock import services
from stock.models import Ajustement, Categorie, Couleur, Modele, Reference, User
from stock.tests.outils import vendre

CHAMPS = ["nom", "categorie", "taille", "couleur", "quantite", "cout", "prix"]


def tableau(*lignes):
    """Données envoyées par le tableau : une liste par champ, une valeur par ligne."""
    donnees = {c: [] for c in CHAMPS}
    for ligne in lignes:
        for c, v in zip(CHAMPS, ligne):
            donnees[c].append(v)
    return donnees


class ArrivageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        cls.lea = User.objects.create_user("lea", password="x")
        cls.pull = Categorie.objects.get(nom="Pull")
        cls.noir, _ = Couleur.objects.get_or_create(nom="Noir")
        # Article déjà eu : vendu, épuisé puis masqué.
        cls.ancien = services.creer_modele("Pull col V", cls.pull, Decimal("14"), Decimal("35"), ["TU"], [cls.noir])
        cls.ancienne = cls.ancien.variantes.get()
        services.ajuster_stock(cls.ancienne.pk, 1, Ajustement.Motif.REASSORT, cls.admin)
        cls.vente = vendre(cls.ancienne.pk, 1, cls.lea)
        Reference.objects.filter(pk=cls.ancienne.pk).update(active=False)

    def setUp(self):
        self.client.force_login(self.admin)

    def verifier(self, *lignes):
        return self.client.post(reverse("arrivage"), {**tableau(*lignes), "verifier": "1"})

    def confirmer(self):
        return self.client.post(reverse("arrivage"), {"confirmer": "1"}, follow=True)

    def test_reserve_aux_administrateurs(self):
        self.client.force_login(self.lea)
        self.assertNotEqual(self.client.get(reverse("arrivage")).status_code, 200)

    def test_page_et_lien_depuis_le_stock(self):
        self.assertContains(self.client.get(reverse("stock_list")), reverse("arrivage"))
        r = self.client.get(reverse("arrivage"))
        self.assertContains(r, "Vérifier l'arrivage")
        self.assertContains(r, "Pull col V")  # proposé pendant la frappe

    def test_arrivage_complet(self):
        r = self.verifier(
            ["Robe portefeuille", "Robe", "S", "Noir", "2", "20", "59"],
            ["", "", "M", "Noir", "1", "", ""],              # même article, valeurs reprises
            ["", "", "M", "blanc/terracotta", "1", "", ""],  # couleur double réécrite proprement
            ["pull COL v", "", "", "Écru", "3", "12,50", ""],  # article déjà eu : repris, nouveau coût
            ["", "", "", "", "", "", ""],
        )
        self.assertContains(r, "Pièces reçues")
        self.assertContains(r, "Enregistrer l'arrivage (7 pièces)")
        self.assertEqual(r.context["recap"]["nouveaux"], 1)
        self.assertEqual(r.context["recap"]["repris"], 1)
        self.assertEqual(r.context["recap"]["valeur"], Decimal("117.50"))  # 4 × 20 + 3 × 12,50
        self.assertFalse(Modele.objects.filter(nom="Robe portefeuille").exists())  # rien avant confirmation

        r = self.confirmer()
        self.assertContains(r, "Arrivage enregistré : 7 pièce(s), 2 article(s)")
        robe = Modele.objects.get(nom="Robe portefeuille")
        self.assertEqual((robe.categorie.nom, robe.cout_achat, robe.prix_vente), ("Robe", Decimal("20.00"), Decimal("59.00")))
        self.assertEqual(sorted((v.taille, v.couleur.nom, v.quantite) for v in robe.variantes.all()),
                         [("M", "Blanc / Terracotta", 1), ("M", "Noir", 1), ("S", "Noir", 2)])
        self.ancien.refresh_from_db()
        self.assertEqual((self.ancien.cout_achat, self.ancien.prix_vente), (Decimal("12.50"), Decimal("35.00")))
        ecru = self.ancien.variantes.get(couleur__nom="Écru")
        self.assertEqual((ecru.quantite, ecru.active), (3, True))
        self.assertEqual(Modele.objects.filter(nom__iexact="pull col v").count(), 1)  # pas de doublon
        self.vente.refresh_from_db()
        self.assertEqual(self.vente.cout_unitaire, Decimal("14.00"))  # l'historique garde l'ancien coût
        self.assertEqual(set(Ajustement.objects.filter(commentaire="Import Excel").values_list("motif", flat=True)),
                         {Ajustement.Motif.REASSORT})
        self.assertContains(self.client.get(reverse("stock_list")), "Robe portefeuille")

    def test_les_pieces_s_ajoutent_au_stock_existant_et_reaffichent(self):
        self.verifier(["Pull col V", "", "", "Noir", "2", "", ""], ["Pull col V", "", "", "Noir", "1", "", ""])
        self.confirmer()
        v = Reference.objects.get(pk=self.ancienne.pk)
        self.assertEqual((v.quantite, v.active), (3, True))  # 0 + 2 + 1, doublon additionné

    def test_erreurs(self):
        r = self.verifier(["Jupe", "Jupe", "", "", "", "10", "30"])
        self.assertContains(r, "indiquez le nombre de pièces reçues")
        r = self.verifier(["Jupe neuve", "Jupe", "", "", "1", "", ""])
        self.assertContains(r, "indiquez le coût d&#x27;achat et le prix de vente")
        r = self.verifier(["", "", "M", "Noir", "1", "10", "30"])
        self.assertContains(r, "indiquez l&#x27;article")
        r = self.verifier(["Jupe", "Jupe", "ZZ", "", "1", "10", "30"])
        self.assertContains(r, "taille « ZZ » inconnue")
        r = self.verifier(["Jupe", "Jupe", "S", "", "1", "10", "30"], ["Jupe", "", "M", "", "1", "12", ""])
        self.assertContains(r, "coût ou prix différents")
        self.assertNotContains(r, "Enregistrer l'arrivage")
        r = self.confirmer()
        self.assertContains(r, "Aucun arrivage en attente")
        self.assertFalse(Modele.objects.filter(nom="Jupe").exists())

    def test_les_lignes_vides_avec_taille_par_defaut_sont_ignorees(self):
        r = self.verifier(["Jupe", "Jupe", "TU", "", "1", "10", "30"], ["", "", "TU", "", "", "", ""],
                          ["", "", "TU", "", "", "", ""])
        self.assertContains(r, "Enregistrer l'arrivage (1 pièce)")

    def test_le_tableau_garde_la_saisie_apres_verification(self):
        r = self.verifier(["Jupe", "Jupe", "", "", "", "10", "30"])
        self.assertContains(r, 'value="Jupe"')
