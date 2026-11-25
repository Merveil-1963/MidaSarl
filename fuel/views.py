import calendar
import csv
from collections import defaultdict
from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError, Sum
from django.http import Http404, FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .context import role
from .forms import BonForm, BusForm, ChauffeurForm, RecuUploadForm, SiteForm
from .models import BonRavitaillement as Bon, Bus, Chauffeur, PlanningAppro as Plan, Site
from .services import INACTIFS, LITRES, cumul_mois, generer_planning

VALIDES = ["valide", "servi"]


def roles_requis(*autorises):
    def deco(vue):
        @wraps(vue)
        @login_required
        def _vue(request, *a, **k):
            r = role(request.user)
            if r is None:
                raise PermissionDenied
            if r not in autorises:
                messages.error(request, "Vous n'avez pas accès à cette page.")
                return redirect("dashboard")
            return vue(request, *a, **k)
        return _vue
    return deco


admin_requis = roles_requis("admin")


def _mois(request):
    t = timezone.localdate()
    try:
        a, m = map(int, request.GET.get("mois", "").split("-"))
        date(a, m, 1)
    except ValueError:
        a, m = t.year, t.month
    prec = (a, m - 1) if m > 1 else (a - 1, 12)
    suiv = (a, m + 1) if m < 12 else (a + 1, 1)
    return a, m, f"{prec[0]}-{prec[1]:02d}", f"{suiv[0]}-{suiv[1]:02d}"


def _ajoute(a, m, k):
    n = a * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


# ---------------------------------------------------------------- Administrateur
@login_required
def dashboard(request):
    r = role(request.user)
    if r == "dg":
        return redirect("kpi")
    if r == "chauffeur":
        return redirect("mes_bons")
    if r is None:
        raise PermissionDenied
    generer_planning()
    t = timezone.localdate()
    bons_mois = Bon.objects.filter(date_bon__year=t.year, date_bon__month=t.month).exclude(statut__in=INACTIFS)
    usage = []
    for b in Bus.objects.filter(actif=True).select_related("site"):
        u = cumul_mois(b, t)
        usage.append({"bus": b, "u": u, "pct": min(100, round(u * 100 / b.quota_mensuel)) if b.quota_mensuel else 0,
                      "depasse": u > b.quota_mensuel})
    usage.sort(key=lambda x: -x["pct"])
    manques = Plan.objects.filter(statut="manque", date_prevue__year=t.year, date_prevue__month=t.month)
    return render(request, "dashboard.html", {
        "aujourdhui": Plan.objects.filter(date_prevue=t).select_related("bus", "bus__site"),
        "manques": manques.select_related("bus")[:8],
        "n_manques": manques.count(),
        "n_a_ravitailler": Plan.objects.filter(date_prevue=t, statut="prevu").count(),
        "n_a_valider": Bon.objects.filter(statut="brouillon").count(),
        "n_hors_quota": bons_mois.filter(hors_quota=True).count(),
        "litres_mois": bons_mois.aggregate(t=Sum(LITRES))["t"] or 0,
        "usage": usage[:8],
        "attendus": Bon.objects.filter(statut="valide").select_related("bus", "chauffeur"),
        "recents": Bon.objects.select_related("bus", "chauffeur")[:6],
        "today": t,
    })


@admin_requis
def calendrier(request):
    generer_planning()
    a, m, prec, suiv = _mois(request)
    semaines = calendar.Calendar(0).monthdatescalendar(a, m)
    plans = Plan.objects.filter(date_prevue__gte=semaines[0][0], date_prevue__lte=semaines[-1][-1]).select_related("bus")
    par_jour = defaultdict(list)
    for p in plans:
        par_jour[p.date_prevue].append(p)
    grille = [[{"jour": j, "autre": j.month != m, "items": par_jour.get(j, [])} for j in sem] for sem in semaines]
    return render(request, "calendrier.html", {
        "grille": grille, "titre": date(a, m, 1), "prec": prec, "suiv": suiv, "today": timezone.localdate()})


@admin_requis
def bons(request):
    qs = Bon.objects.select_related("bus", "chauffeur")
    statut, q = request.GET.get("statut", ""), request.GET.get("q", "").strip()
    if statut == "hors_quota":
        qs = qs.filter(hors_quota=True)
    elif statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(bus__plaque__icontains=q) | qs.filter(chauffeur__nom__icontains=q)
    return render(request, "bons.html", {"bons": qs[:100], "statut": statut, "q": q, "statuts": Bon.Statut.choices})


@admin_requis
def bon_nouveau(request):
    initial = {"date_bon": timezone.localdate()}
    if request.GET.get("planning"):
        p = get_object_or_404(Plan, pk=request.GET["planning"])
        initial.update(planning=p, bus=p.bus, date_bon=p.date_prevue, litres_autorises=p.litres_prevus)
    form = BonForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        bon = form.save(commit=False)
        bon.type_carburant = bon.bus.type_carburant
        bon.depassement_litres = form.depassement
        bon.hors_quota = form.depassement > 0
        bon.cree_par = request.user
        valider = "valider" in request.POST
        if valider:
            bon.statut, bon.valide_par, bon.date_validation = "valide", request.user, timezone.now()
        bon.save()
        if bon.planning:
            Plan.objects.filter(pk=bon.planning_id).update(statut="emis")
        messages.success(request, f"Bon n° {bon.numero} créé" + (" et validé." if valider else ". Pensez à le valider."))
        return redirect("bon_detail", pk=bon.pk)
    return render(request, "bon_form.html", {"form": form})


def _libere_planning(bon):
    if bon.planning_id:
        Plan.objects.filter(pk=bon.planning_id).update(
            statut="manque" if bon.planning.date_prevue < timezone.localdate() else "prevu")


def _enregistre_recu(bon, fichier):
    """Le reçu déposé clôture le bon : statut Servi et passage du planning en Réalisé."""
    if bon.recu_fichier:
        bon.recu_fichier.delete(save=False)
    bon.recu_fichier = fichier
    bon.recu_depose_le = timezone.now()
    bon.statut = "servi"
    bon.save()
    if bon.planning_id:
        Plan.objects.filter(pk=bon.planning_id).update(statut="realise")


@admin_requis
def bon_detail(request, pk):
    bon = get_object_or_404(Bon.objects.select_related("bus", "chauffeur", "cree_par", "valide_par"), pk=pk)
    upload_form = RecuUploadForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("valider", "refuser") and bon.statut == "brouillon":
            bon.statut = "valide" if action == "valider" else "refuse"
            bon.valide_par, bon.date_validation = request.user, timezone.now()
            bon.save()
            if action == "refuser":
                _libere_planning(bon)
            messages.success(request, "Bon validé." if action == "valider" else "Bon refusé.")
        elif action == "annuler" and bon.statut in ("brouillon", "valide"):
            bon.statut = "annule"
            bon.save()
            _libere_planning(bon)
            messages.success(request, "Bon annulé.")
        elif action == "recu" and bon.statut in ("valide", "servi"):
            upload_form = RecuUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                _enregistre_recu(bon, upload_form.cleaned_data["fichier"])
                messages.success(request, "Reçu enregistré. Bon clôturé.")
                return redirect("bon_detail", pk=bon.pk)
            return render(request, "bon_detail.html", {"bon": bon, "upload_form": upload_form})
        return redirect("bon_detail", pk=bon.pk)
    return render(request, "bon_detail.html", {"bon": bon, "upload_form": upload_form})


@admin_requis
def bon_imprimer(request, pk):
    bon = get_object_or_404(Bon.objects.select_related("bus", "chauffeur"), pk=pk)
    return render(request, "bon_print.html", {"bon": bon})


@login_required
def bon_recu(request, pk):
    """Sert le fichier du reçu : administrateur, ou chauffeur propriétaire du bon."""
    bon = get_object_or_404(Bon, pk=pk)
    r = role(request.user)
    autorise = r == "admin" or (r == "chauffeur" and bon.chauffeur.user_id == request.user.id)
    if not autorise or not bon.recu_fichier:
        raise Http404
    return FileResponse(bon.recu_fichier.open("rb"))


@admin_requis
def api_quota(request):
    try:
        bus = Bus.objects.get(pk=request.GET["bus"])
        jour = date.fromisoformat(request.GET["date"])
        litres = int(request.GET.get("litres") or 0)
    except (KeyError, ValueError, Bus.DoesNotExist):
        return JsonResponse({}, status=400)
    c = cumul_mois(bus, jour)
    return JsonResponse({"cumul": c, "quota": bus.quota_mensuel, "restant": bus.quota_mensuel - c,
                         "depassement": max(0, c + litres - bus.quota_mensuel), "litres_standard": bus.litres_standard})


@admin_requis
def rapports(request):
    a, m, prec, suiv = _mois(request)
    jour = date(a, m, 1)
    lignes, par_carb, par_site, par_chauf = [], defaultdict(int), defaultdict(int), defaultdict(int)
    for b in Bus.objects.select_related("site"):
        qs = Bon.objects.filter(bus=b, date_bon__year=a, date_bon__month=m).exclude(statut__in=INACTIFS)
        litres = qs.aggregate(t=Sum(LITRES))["t"] or 0
        lignes.append({"bus": b, "passages": qs.count(), "litres": litres, "restant": b.quota_mensuel - litres,
                       "pct": min(100, round(litres * 100 / b.quota_mensuel)) if b.quota_mensuel else 0})
        par_carb[b.type_carburant] += litres
        par_site[b.site.nom] += litres
    hors = Bon.objects.filter(date_bon__year=a, date_bon__month=m, hors_quota=True).exclude(statut__in=INACTIFS).select_related("bus", "chauffeur")
    for ch in Chauffeur.objects.all():
        t = Bon.objects.filter(chauffeur=ch, date_bon__year=a, date_bon__month=m).exclude(statut__in=INACTIFS).aggregate(t=Sum(LITRES))["t"] or 0
        if t:
            par_chauf[ch.nom] = t
    if request.GET.get("export") == "csv":
        rep = HttpResponse(content_type="text/csv; charset=utf-8")
        rep["Content-Disposition"] = f'attachment; filename="rapport-carburant-{a}-{m:02d}.csv"'
        rep.write("\ufeff")
        w = csv.writer(rep, delimiter=";")
        w.writerow(["Plaque", "Site", "Carburant", "Passages", "Litres", "Quota", "Restant"])
        for l in lignes:
            w.writerow([l["bus"].plaque, l["bus"].site.nom, l["bus"].type_carburant, l["passages"], l["litres"], l["bus"].quota_mensuel, l["restant"]])
        return rep
    return render(request, "rapports.html", {
        "lignes": lignes, "par_carb": dict(par_carb), "par_site": dict(par_site), "par_chauf": dict(par_chauf),
        "hors": hors, "titre": jour, "mois": f"{a}-{m:02d}", "prec": prec, "suiv": suiv})


CONFIG = {
    "bus": dict(model=Bus, form=BusForm, titre="Bus", un="un bus",
                cols=[("Plaque", "plaque"), ("Site", "site"), ("Carburant", "type_carburant"), ("Litres/passage", "litres_standard"),
                      ("Quota", "quota_mensuel"), ("Début du cycle", "date_debut_cycle"), ("Tous les (j)", "intervalle_jours"), ("Actif", "actif")]),
    "chauffeurs": dict(model=Chauffeur, form=ChauffeurForm, titre="Chauffeurs", un="un chauffeur",
                       cols=[("Nom", "nom"), ("Téléphone", "telephone"), ("Compte", "compte"), ("Actif", "actif")]),
    "sites": dict(model=Site, form=SiteForm, titre="Sites", un="un site", cols=[("Nom", "nom")]),
}


def _cfg(cle):
    if cle not in CONFIG:
        raise Http404
    return CONFIG[cle]


def _fmt(v):
    if isinstance(v, bool):
        return "Oui" if v else "Non"
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return "" if v is None else str(v)


@admin_requis
def liste(request, cle):
    c = _cfg(cle)
    lignes = [{"obj": o, "cells": [_fmt(getattr(o, a)) for _, a in c["cols"]]} for o in c["model"].objects.all()]
    return render(request, "liste.html", {"cle": cle, "c": c, "colonnes": [l for l, _ in c["cols"]], "lignes": lignes})


@admin_requis
def edition(request, cle, pk=None):
    c = _cfg(cle)
    obj = get_object_or_404(c["model"], pk=pk) if pk else None
    form = c["form"](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Enregistré.")
        return redirect("liste", cle=cle)
    return render(request, "form.html", {"form": form, "cle": cle, "c": c, "obj": obj})


@admin_requis
def suppression(request, cle, pk):
    c = _cfg(cle)
    obj = get_object_or_404(c["model"], pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Supprimé.")
        except ProtectedError:
            messages.error(request, "Suppression impossible : des bons utilisent cet élément. Désactivez-le plutôt.")
    return redirect("liste", cle=cle)


# ---------------------------------------------------------------- Directeur général
@roles_requis("admin", "dg")
def kpi(request):
    generer_planning()
    a, m, prec, suiv = _mois(request)
    t = timezone.localdate()
    base = Bon.objects.filter(statut__in=VALIDES)
    mois = base.filter(date_bon__year=a, date_bon__month=m)

    def somme(qs):
        return qs.aggregate(t=Sum(LITRES))["t"] or 0

    litres_mois = somme(mois)
    pa, pm = _ajoute(a, m, -1)
    litres_prec = somme(base.filter(date_bon__year=pa, date_bon__month=pm))
    variation = round((litres_mois - litres_prec) * 100 / litres_prec, 1) if litres_prec else None

    evol = {"labels": [], "values": []}
    for k in range(-5, 1):
        y, mo = _ajoute(a, m, k)
        evol["labels"].append(f"{mo:02d}/{y}")
        evol["values"].append(somme(base.filter(date_bon__year=y, date_bon__month=mo)))

    plans = Plan.objects.filter(date_prevue__year=a, date_prevue__month=m, date_prevue__lte=t)
    prevus, realises = plans.count(), plans.filter(statut="realise").count()

    par_bus, depassants = [], []
    for b in Bus.objects.filter(actif=True).select_related("site"):
        l = somme(mois.filter(bus=b))
        ligne = {"bus": b, "litres": l, "pct": min(100, round(l * 100 / b.quota_mensuel)) if b.quota_mensuel else 0,
                 "depasse": l > b.quota_mensuel}
        par_bus.append(ligne)
        if ligne["depasse"]:
            depassants.append(ligne)
    par_bus.sort(key=lambda x: -x["litres"])
    sous_quota = sum(1 for x in par_bus if not x["depasse"])

    def groupe(champ):
        return list(mois.values(champ).annotate(total=Sum(LITRES)).order_by("-total"))

    carb, site, chauf = groupe("type_carburant"), groupe("bus__site__nom"), groupe("chauffeur__nom")[:5]
    mx = max([x["total"] for x in site], default=0)
    par_site = [{"nom": x["bus__site__nom"], "total": x["total"], "pct": round(x["total"] * 100 / mx) if mx else 0} for x in site]
    hors = mois.filter(hors_quota=True)
    graph = {"evol": evol,
             "carb": {"labels": [x["type_carburant"] for x in carb], "values": [x["total"] for x in carb]},
             "site": {"labels": [x["bus__site__nom"] for x in site], "values": [x["total"] for x in site]}}
    return render(request, "kpi.html", {
        "titre": date(a, m, 1), "prec": prec, "suiv": suiv, "mois": f"{a}-{m:02d}",
        "litres_mois": litres_mois, "variation": variation, "n_bons": mois.count(),
        "taux_real": round(realises * 100 / prevus) if prevus else None, "realises": realises, "prevus": prevus,
        "taux_quota": round(sous_quota * 100 / len(par_bus)) if par_bus else None,
        "n_hors": hors.count(), "l_hors": hors.aggregate(t=Sum("depassement_litres"))["t"] or 0,
        "retards": Bon.objects.filter(statut="valide", date_bon__lt=t - timedelta(days=2)).count(),
        "n_a_valider": Bon.objects.filter(statut="brouillon").count(),
        "par_site": par_site, "top_bus": par_bus[:6], "depassants": depassants, "top_chauf": chauf, "graph": graph})


# ---------------------------------------------------------------- Chauffeur
def _chauffeur(request):
    try:
        return request.user.chauffeur
    except Chauffeur.DoesNotExist:
        raise PermissionDenied


@roles_requis("chauffeur")
def mes_bons(request):
    ch = _chauffeur(request)
    qs = Bon.objects.filter(chauffeur=ch).exclude(statut="brouillon").select_related("bus")
    return render(request, "mes_bons.html", {
        "ch": ch, "a_deposer": qs.filter(statut="valide"), "autres": qs.exclude(statut="valide")[:30]})


@roles_requis("chauffeur")
def mon_bon(request, pk):
    ch = _chauffeur(request)
    bon = get_object_or_404(Bon.objects.select_related("bus"), pk=pk, chauffeur=ch)
    if bon.statut == "brouillon":
        raise Http404
    form = RecuUploadForm()
    if request.method == "POST":
        if bon.statut not in ("valide", "servi"):
            messages.error(request, "Ce bon n'accepte plus de reçu.")
        else:
            form = RecuUploadForm(request.POST, request.FILES)
            if form.is_valid():
                _enregistre_recu(bon, form.cleaned_data["fichier"])
                messages.success(request, "Reçu envoyé. Votre bon est clôturé.")
                return redirect("mon_bon", pk=bon.pk)
    return render(request, "mon_bon.html", {"bon": bon, "form": form})
