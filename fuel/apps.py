from django.apps import AppConfig
from django.db.models.signals import post_migrate


def creer_groupes(sender, **kwargs):
    from django.contrib.auth.models import Group
    for nom in ("Administrateur", "DG", "Chauffeur"):
        Group.objects.get_or_create(name=nom)


class FuelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fuel"
    verbose_name = "Gestion du carburant"

    def ready(self):
        post_migrate.connect(creer_groupes, sender=self)
