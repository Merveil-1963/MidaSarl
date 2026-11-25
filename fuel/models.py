from django.conf import settings
from django.db import models
from django.db.models import Max


class Carburant(models.TextChoices):
    ESSENCE = "Essence", "Essence"
    DIESEL = "Diesel", "Diesel"


class Site(models.Model):
    nom = models.CharField("Nom", max_length=100, unique=True)

    class Meta:
        ordering = ["nom"]``

    def __str__(self):
        return self.nom


class Chauffeur(models.Model):
    nom = models.CharField("Nom", max_length=120)
    matricule = models.CharField("Matricule", max_length=30, blank=True)
    poste = models.CharField("Poste", max_length=100, blank=True)
    departement = models.CharField("Département", max_length=100, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    actif = models.BooleanField("Actif", default=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="Compte", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="chauffeur")

    class Meta:
        ordering = ["nom"]

    @property
    def compte(self):
        return self.user.username if self.user_id else "-"

    def __str__(self):
        return self.nom


class Bus(models.Model):
    plaque = models.CharField("Plaque", max_length=30, unique=True)
    site = models.ForeignKey(Site, verbose_name="Site", on_delete=models.PROTECT)
    type_carburant = models.CharField("Carburant", max_length=10, choices=Carburant.choices)
    litres_standard = models.PositiveIntegerField("Litres par passage")
    quota_mensuel = models.PositiveIntegerField("Quota mensuel (L)")
    date_debut_cycle = models.DateField("Début du cycle")
    intervalle_jours = models.PositiveSmallIntegerField("Intervalle (jours)", default=3)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["plaque"]
        verbose_name_plural = "bus"

    def __str__(self):
        return self.plaque


class PlanningAppro(models.Model):
    class Statut(models.TextChoices):
        PREVU = "prevu", "Prévu"
        EMIS = "emis", "Bon émis"
        REALISE = "realise", "Réalisé"
        MANQUE = "manque", "Manqué"

    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="plannings")
    date_prevue = models.DateField()
    litres_prevus = models.PositiveIntegerField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PREVU)

    class Meta:
        ordering = ["date_prevue", "bus__plaque"]
        constraints = [models.UniqueConstraint(fields=["bus", "date_prevue"], name="planning_unique")]

    def __str__(self):
        return f"{self.bus} - {self.date_prevue}"


class BonRavitaillement(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDE = "valide", "Validé"
        SERVI = "servi", "Servi (reçu déposé)"
        ANNULE = "annule", "Annulé"
        REFUSE = "refuse", "Refusé"

    numero = models.PositiveIntegerField("N°", unique=True, editable=False)
    date_bon = models.DateField("Date")
    planning = models.OneToOneField(PlanningAppro, null=True, blank=True, on_delete=models.SET_NULL, related_name="bon")
    bus = models.ForeignKey(Bus, verbose_name="Bus", on_delete=models.PROTECT, related_name="bons")
    chauffeur = models.ForeignKey(Chauffeur, verbose_name="Chauffeur", on_delete=models.PROTECT, related_name="bons")
    type_carburant = models.CharField("Carburant", max_length=10, choices=Carburant.choices)
    litres_autorises = models.PositiveIntegerField("Litres autorisés")
    recu_fichier = models.FileField("Reçu (photo ou PDF)", upload_to="recus/%Y/%m/", null=True, blank=True)
    recu_depose_le = models.DateTimeField("Reçu déposé le", null=True, blank=True)
    hors_quota = models.BooleanField("Hors quota", default=False)
    depassement_litres = models.PositiveIntegerField("Dépassement (L)", default=0)
    motif_depassement = models.TextField("Motif du dépassement", blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="bons_crees")
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="bons_valides")
    date_validation = models.DateTimeField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-numero"]

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = (BonRavitaillement.objects.aggregate(m=Max("numero"))["m"] or 600) + 1
        super().save(*args, **kwargs)

    @property
    def recu_est_image(self):
        return bool(self.recu_fichier) and self.recu_fichier.name.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp")

    def __str__(self):
        return f"Bon n° {self.numero}"
