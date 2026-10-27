import json

from django.test import TestCase
from django.urls import reverse

from stock.models import User


class ApplicationInstallableTests(TestCase):
    def test_manifeste(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        m = json.loads(r.content)
        self.assertEqual(m["short_name"], "Maison d'Annaé")
        self.assertEqual(m["display"], "standalone")
        self.assertEqual(m["start_url"], "/")
        tailles = {(i["sizes"], i["purpose"]) for i in m["icons"]}
        self.assertTrue({("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= tailles)

    def test_service_worker_a_la_racine(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/javascript")
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        self.assertIn("/hors-ligne/", r.content.decode())

    def test_page_hors_ligne_sans_connexion_au_compte(self):
        r = self.client.get(reverse("hors_ligne"))
        self.assertContains(r, "Pas de connexion")

    def test_pages_declarent_l_application(self):
        self.client.force_login(User.objects.create_user("lea", password="x"))
        r = self.client.get(reverse("stock_list"))
        self.assertContains(r, 'rel="manifest"')
        self.assertContains(r, 'rel="apple-touch-icon"')
        self.assertContains(r, "serviceWorker.register")
        # La page de connexion aussi : c'est elle qui s'ouvre au premier lancement.
        self.client.logout()
        self.assertContains(self.client.get(reverse("login")), 'rel="manifest"')
