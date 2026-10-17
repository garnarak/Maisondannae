from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from stock.models import User


class EnsureAdminTests(TestCase):
    def test_cree_le_compte_une_seule_fois(self):
        env = {"DJANGO_ADMIN_USERNAME": "garnik", "DJANGO_ADMIN_PASSWORD": "motdepasse-long-42"}
        with _env(env):
            call_command("ensure_admin", stdout=_Silence())
            admin = User.objects.get(username="garnik")
            self.assertTrue(admin.is_admin)
            self.assertTrue(admin.check_password("motdepasse-long-42"))
            with _env({**env, "DJANGO_ADMIN_PASSWORD": "autre"}):
                call_command("ensure_admin", stdout=_Silence())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("motdepasse-long-42"))
        self.assertEqual(User.objects.count(), 1)

    def test_sans_variables_ne_fait_rien(self):
        with _env({"DJANGO_ADMIN_USERNAME": "", "DJANGO_ADMIN_PASSWORD": ""}):
            call_command("ensure_admin", stdout=_Silence())
        self.assertFalse(User.objects.exists())


@override_settings(DEBUG=False)
class PagesErreurTests(TestCase):
    def test_403_en_francais(self):
        self.client.force_login(User.objects.create_user("lea", password="x"))
        r = self.client.get(reverse("marge"))
        self.assertContains(r, "Accès refusé", status_code=403)
        self.assertContains(r, "Version", status_code=403)


def _env(values):
    from unittest import mock

    return mock.patch.dict("os.environ", values)


class _Silence:
    def write(self, *args, **kwargs):
        pass

    def flush(self):
        pass
