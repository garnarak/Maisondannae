from django.core.management.base import BaseCommand
from django.db import transaction

from stock.models import Ajustement, RecuperationEspeces, Reference, Vente


class Command(BaseCommand):
    help = (
        "Supprime toutes les données de stock (références, ventes, ajustements, récupérations "
        "d'espèces) pour repartir de zéro. Les comptes utilisateurs sont conservés. "
        "Sans --confirmer, affiche seulement ce qui serait supprimé."
    )

    def add_arguments(self, parser):
        parser.add_argument("--confirmer", action="store_true", help="Effectuer réellement la suppression.")

    def handle(self, *args, confirmer=False, **options):
        # Ordre imposé : une vente protège sa référence, elle doit partir avant elle.
        tables = [
            ("récupérations d'espèces", RecuperationEspeces),
            ("ventes", Vente),
            ("ajustements de stock", Ajustement),
            ("références", Reference),
        ]
        for libelle, modele in tables:
            self.stdout.write(f"  {modele.objects.count():>6}  {libelle}")

        if not confirmer:
            self.stdout.write(self.style.WARNING(
                "\nRien n'a été supprimé. Pour supprimer ces données, relancez avec --confirmer."
            ))
            return

        with transaction.atomic():
            for _, modele in tables:
                modele.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(
            "\nDonnées de test supprimées. Les comptes utilisateurs sont conservés. "
            "La caisse repart avec un fond de 30 € jusqu'à la première récupération."
        ))
