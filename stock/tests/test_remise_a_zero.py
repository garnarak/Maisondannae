from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from stock import services
from stock.models import Ajustement, RecuperationEspeces, Reference, User, Vente
from stock.tests.outils import vendre


class RemiseAZeroTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("garnik", password="x", role=User.Role.ADMIN)
        self.lea = User.objects.create_user("lea", password="x")
        robe = Reference.objects.create(
            designation="Robe lin", cout_achat=Decimal("30"), prix_vente=Decimal("50"), quantite=10
        )
        vendre(robe.pk, 1, self.lea, paiement="especes")
        services.ajuster_stock(robe.pk, 2, Ajustement.Motif.REASSORT, self.admin)
        services.recuperer_especes(self.admin)

    def test_sans_confirmation_rien_n_est_supprime(self):
        sortie = StringIO()
        call_command("vider_donnees_de_test", stdout=sortie)
        self.assertIn("Rien n'a été supprimé", sortie.getvalue())
        self.assertEqual(Reference.objects.count(), 1)
        self.assertEqual(Vente.objects.count(), 1)

    def test_avec_confirmation_tout_est_supprime_sauf_les_comptes(self):
        call_command("vider_donnees_de_test", "--confirmer", stdout=StringIO())
        for modele in (Reference, Vente, Ajustement, RecuperationEspeces):
            self.assertFalse(modele.objects.exists(), modele.__name__)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(services.especes_en_caisse(), Decimal("30.00"))
