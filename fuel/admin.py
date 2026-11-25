from django.contrib import admin

from .models import BonRavitaillement, Bus, Chauffeur, PlanningAppro, Site

admin.site.site_header = "Gestion du carburant"
for m in (Site, Chauffeur, Bus, PlanningAppro, BonRavitaillement):
    admin.site.register(m)
