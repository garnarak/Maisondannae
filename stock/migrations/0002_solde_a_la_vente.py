from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def remplir_prix_catalogue(apps, schema_editor):
    # Ventes antérieures : aucune remise, le prix catalogue est le prix encaissé.
    apps.get_model("stock", "Vente").objects.update(prix_catalogue=F("prix_unitaire"))


class Migration(migrations.Migration):
    dependencies = [("stock", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="vente",
            name="prix_catalogue",
            field=models.DecimalField(
                "prix de vente initial", max_digits=10, decimal_places=2, default=Decimal("0"),
                help_text="Prix de la référence au moment de la vente, avant solde.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="vente",
            name="remise_pct",
            field=models.PositiveSmallIntegerField(
                "solde (%)", default=0,
                choices=[(0, "Aucun"), (10, "10 %"), (20, "20 %"), (30, "30 %"), (40, "40 %"), (50, "50 %"), (70, "70 %")],
            ),
        ),
        migrations.AlterField(
            model_name="vente",
            name="prix_unitaire",
            field=models.DecimalField("prix encaissé", max_digits=10, decimal_places=2, help_text="Prix après solde."),
        ),
        migrations.RunPython(remplir_prix_catalogue, migrations.RunPython.noop),
    ]
