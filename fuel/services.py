from datetime import timedelta

from django.db.models import F, Sum
from django.utils import timezone

from .models import Bus, BonRavitaillement, PlanningAppro

INACTIFS = [BonRavitaillement.Statut.ANNULE, BonRavitaillement.Statut.REFUSE]
LITRES = F("litres_autorises")


def cumul_mois(bus, jour):
    """Litres du mois pour un bus (litres des bons, hors annulés et refusés)."""
    qs = BonRavitaillement.objects.filter(
        bus=bus, date_bon__year=jour.year, date_bon__month=jour.month
    ).exclude(statut__in=INACTIFS)
    return qs.aggregate(t=Sum(LITRES))["t"] or 0


def generer_planning(jours=45):
    """Crée les passages prévus (tous les N jours, en continu) et marque les passages manqués."""
    today = timezone.localdate()
    fin = today + timedelta(days=jours)
    debut = today - timedelta(days=45)
    nouveaux = []
    for bus in Bus.objects.filter(actif=True):
        pas = max(bus.intervalle_jours, 1)
        d = bus.date_debut_cycle
        if d < debut:
            d += timedelta(days=-(-(debut - d).days // pas) * pas)
        while d <= fin:
            nouveaux.append(PlanningAppro(bus=bus, date_prevue=d, litres_prevus=bus.litres_standard))
            d += timedelta(days=pas)
    PlanningAppro.objects.bulk_create(nouveaux, ignore_conflicts=True)
    PlanningAppro.objects.filter(
        statut=PlanningAppro.Statut.PREVU, date_prevue__lt=today
    ).update(statut=PlanningAppro.Statut.MANQUE)
