from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import path, reverse

from stock.models import User


def vue_en_erreur(request):
    raise RuntimeError("panne simulée")


urlpatterns = [path("erreur/", vue_en_erreur)]


class VersionProductionTests(TestCase):
    def test_plus_de_mention_beta(self):
        self.client.force_login(User.objects.create_user("lea", password="x"))
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, f"Version {settings.APP_VERSION}")
        self.assertNotContains(r, "Bêta")


@override_settings(ROOT_URLCONF=__name__, DEBUG=False, ADMINS=[("garnik", "garnik@exemple.fr")])
class AlertesParEmailTests(TestCase):
    def test_une_erreur_envoie_un_email_aux_administrateurs(self):
        client = Client(raise_request_exception=False)
        r = client.get("/erreur/")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["garnik@exemple.fr"])
        self.assertIn("[Maison d'Annaé]", mail.outbox[0].subject)
        self.assertIn("panne simulée", mail.outbox[0].body)
        self.assertContains(r, "Une erreur s'est produite", status_code=500)

    @override_settings(ADMINS=[])
    def test_sans_administrateur_configure_aucun_email(self):
        Client(raise_request_exception=False).get("/erreur/")
        self.assertEqual(len(mail.outbox), 0)
