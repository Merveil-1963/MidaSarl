from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from fuel.models import BonRavitaillement, Bus, Chauffeur, PlanningAppro, Site
from fuel.services import generer_planning

BUS = [
    ("9766 AB/14", "WAZ", "Essence", 75, 850), ("6816 AA/14", "BIG SERVICE", "Diesel", 90, 850),
    ("2343 AC/14", "WAZ HOSPITALITY", "Diesel", 80, 850), ("9765 AB/04", "WAZ HOSPITALITY", "Essence", 90, 850),
    ("2299 AC/14", "KILELE", "Diesel", 90, 850), ("6924 AX/05", "FAC", "Essence", 75, 850),
    ("3261 AC/14", "FAC", "Diesel", 90, 850), ("3001 AC/14", "BUREAU", "Essence", 90, 850),
    ("2715 AY/05", "BIG SERVICE", "Essence", 80, 500), ("2714 AY/05", "BIG SERVICE", "Essence", 75, 850),
]
CHAUFFEURS = ["André Mavungu", "Jean Kalala", "Paul Mutombo", "Joseph Ilunga"]


class Command(BaseCommand):
    help = "Crée des données de démonstration et des comptes (administrateur, DG, chauffeur)."

    def handle(self, *args, **opts):
        g_admin, g_dg, g_ch = [Group.objects.get_or_create(name=n)[0] for n in ("Administrateur", "DG", "Chauffeur")]
        if not User.objects.filter(username="admin").exists():
            u = User.objects.create_superuser("admin", password="admin123", first_name="Administrateur")
            u.groups.add(g_admin)
        if not User.objects.filter(username="dg").exists():
            User.objects.create_user("dg", password="dg123", first_name="Directeur général").groups.add(g_dg)
        admin = User.objects.get(username="admin")
        today = timezone.localdate()
        chauffeurs = [Chauffeur.objects.get_or_create(nom=n)[0] for n in CHAUFFEURS]
        premier = chauffeurs[0]
        if not premier.user_id:
            u = User.objects.create_user("andre", password="andre123", first_name=premier.nom)
            u.groups.add(g_ch)
            premier.user = u
            premier.save()
        for i, (pl, site, carb, litres, quota) in enumerate(BUS):
            s, _ = Site.objects.get_or_create(nom=site)
            Bus.objects.get_or_create(plaque=pl, defaults=dict(
                site=s, type_carburant=carb, litres_standard=litres, quota_mensuel=quota,
                date_debut_cycle=today - timedelta(days=21 - i % 3), intervalle_jours=3))
        generer_planning()
        if not BonRavitaillement.objects.exists():
            for k, p in enumerate(PlanningAppro.objects.filter(date_prevue__lt=today, date_prevue__gte=today - timedelta(days=20)).select_related("bus")):
                if k % 17 == 5:
                    continue  # laisse quelques passages manqués
                BonRavitaillement.objects.create(
                    date_bon=p.date_prevue, planning=p, bus=p.bus, chauffeur=chauffeurs[k % len(chauffeurs)],
                    type_carburant=p.bus.type_carburant, litres_autorises=p.litres_prevus,
                    statut="servi", cree_par=admin, valide_par=admin,
                    date_validation=timezone.now())
                PlanningAppro.objects.filter(pk=p.pk).update(statut="realise")
        self.stdout.write(self.style.SUCCESS(
            "Démo prête. Comptes : admin/admin123 (administrateur), dg/dg123 (DG), andre/andre123 (chauffeur)."))
