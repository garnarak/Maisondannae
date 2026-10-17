import os

from django.core.management.base import BaseCommand

from stock.models import User


class Command(BaseCommand):
    help = (
        "Crée le compte administrateur à partir de DJANGO_ADMIN_USERNAME et DJANGO_ADMIN_PASSWORD "
        "s'il n'existe pas encore. Ne modifie jamais un compte existant."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_ADMIN_USERNAME")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")
        if not username or not password:
            self.stdout.write("DJANGO_ADMIN_USERNAME / DJANGO_ADMIN_PASSWORD absents : rien à faire.")
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Le compte « {username} » existe déjà.")
            return
        User.objects.create_superuser(username=username, email="", password=password)
        self.stdout.write(self.style.SUCCESS(f"Compte administrateur « {username} » créé."))
