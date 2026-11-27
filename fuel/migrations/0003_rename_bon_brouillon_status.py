from django.db import migrations, models


def renommer_brouillon_en_approuve(apps, schema_editor):
    BonRavitaillement = apps.get_model("fuel", "BonRavitaillement")
    BonRavitaillement.objects.filter(statut="brouillon").update(statut="approuve")


def annuler_renommage(apps, schema_editor):
    BonRavitaillement = apps.get_model("fuel", "BonRavitaillement")
    BonRavitaillement.objects.filter(statut="approuve").update(statut="brouillon")


class Migration(migrations.Migration):

    dependencies = [
        ("fuel", "0002_chauffeur_departement_chauffeur_matricule_and_more"),
    ]

    operations = [
        migrations.RunPython(renommer_brouillon_en_approuve, annuler_renommage),
        migrations.AlterField(
            model_name="bonravitaillement",
            name="statut",
            field=models.CharField(
                choices=[
                    ("approuve", "Approuvé"),
                    ("valide", "Validé"),
                    ("servi", "Servi (reçu déposé)"),
                    ("annule", "Annulé"),
                    ("refuse", "Refusé"),
                ],
                default="approuve",
                max_length=10,
            ),
        ),
    ]
