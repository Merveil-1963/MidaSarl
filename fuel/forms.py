from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import BonRavitaillement, Bus, Chauffeur, PlanningAppro, Site
from .services import cumul_mois


def date_widget():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["nom"]


class ChauffeurForm(forms.ModelForm):
    identifiant = forms.CharField(label="Identifiant de connexion", required=False,
                                  help_text="Laissez vide si ce chauffeur n'a pas de compte.")
    mot_de_passe = forms.CharField(label="Mot de passe", required=False, widget=forms.PasswordInput(render_value=False),
                                   help_text="Obligatoire à la création du compte. Laissez vide pour ne pas le changer.")
    confirmation_mot_de_passe = forms.CharField(label="Confirmer le mot de passe", required=False,
                                                widget=forms.PasswordInput(render_value=False))

    class Meta:
        model = Chauffeur
        fields = ["nom", "matricule", "poste", "departement", "telephone", "actif"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.user_id:
            self.fields["identifiant"].initial = self.instance.user.username

    def clean_identifiant(self):
        v = (self.cleaned_data.get("identifiant") or "").strip()
        if v:
            qs = User.objects.filter(username__iexact=v)
            if self.instance.user_id:
                qs = qs.exclude(pk=self.instance.user_id)
            if qs.exists():
                raise ValidationError("Cet identifiant existe déjà.")
        return v

    def clean(self):
        d = super().clean()
        ident = d.get("identifiant")
        pw = d.get("mot_de_passe")
        confirmation = d.get("confirmation_mot_de_passe")

        if ident and not self.instance.user_id and not pw:
            self.add_error("mot_de_passe", "Mot de passe obligatoire pour créer le compte.")
        if pw:
            if len(pw) < 6:
                self.add_error("mot_de_passe", "6 caractères minimum.")
            if pw != confirmation:
                self.add_error("confirmation_mot_de_passe", "Les mots de passe ne correspondent pas.")
            else:
                user = self.instance.user if self.instance.user_id else User(username=ident or "chauffeur")
                try:
                    validate_password(pw, user)
                except ValidationError as exc:
                    self.add_error("mot_de_passe", exc)
        elif confirmation:
            self.add_error("mot_de_passe", "Entrez le mot de passe, puis confirmez-le.")
        return d

    def save(self, commit=True):
        ch = super().save(commit=commit)
        ident, pw = self.cleaned_data.get("identifiant"), self.cleaned_data.get("mot_de_passe")
        if ident:
            u = ch.user if ch.user_id else User(username=ident)
            u.username = ident
            u.first_name = ch.nom[:150]
            u.is_active = ch.actif
            if pw:
                u.set_password(pw)
            u.save()
            u.groups.add(Group.objects.get_or_create(name="Chauffeur")[0])
            if not ch.user_id:
                ch.user = u
                ch.save()
        return ch


class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ["plaque", "site", "type_carburant", "litres_standard", "quota_mensuel",
                  "date_debut_cycle", "intervalle_jours", "actif"]
        widgets = {"date_debut_cycle": date_widget()}

    def clean_plaque(self):
        return self.cleaned_data["plaque"].strip().upper()

    def clean_intervalle_jours(self):
        v = self.cleaned_data["intervalle_jours"]
        if v < 1:
            raise forms.ValidationError("L'intervalle doit être d'au moins 1 jour.")
        return v


class BonForm(forms.ModelForm):
    planning = forms.ModelChoiceField(PlanningAppro.objects.all(), required=False, widget=forms.HiddenInput)

    class Meta:
        model = BonRavitaillement
        fields = ["planning", "bus", "chauffeur", "date_bon", "litres_autorises", "motif_depassement"]
        widgets = {"date_bon": date_widget(), "motif_depassement": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bus"].queryset = Bus.objects.filter(actif=True)
        self.fields["chauffeur"].queryset = Chauffeur.objects.filter(actif=True)
        self.depassement = 0

    def clean_litres_autorises(self):
        v = self.cleaned_data["litres_autorises"]
        if v <= 0:
            raise forms.ValidationError("Entrez un nombre de litres positif.")
        return v

    def clean(self):
        data = super().clean()
        bus, jour, litres = data.get("bus"), data.get("date_bon"), data.get("litres_autorises")
        if bus and jour and litres:
            self.depassement = max(0, cumul_mois(bus, jour) + litres - bus.quota_mensuel)
            if self.depassement and not (data.get("motif_depassement") or "").strip():
                self.add_error("motif_depassement",
                               f"Dépassement de {self.depassement} L : un motif est obligatoire.")
        return data


class RecuUploadForm(forms.Form):
    """Dépôt du reçu (photo ou PDF) par le chauffeur."""
    fichier = forms.FileField(label="Photo ou PDF du reçu", widget=forms.FileInput(attrs={"accept": "image/*,.pdf"}))

    def clean_fichier(self):
        f = self.cleaned_data["fichier"]
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in ("jpg", "jpeg", "png", "webp", "pdf"):
            raise forms.ValidationError("Formats acceptés : JPG, PNG, WEBP ou PDF.")
        if f.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Fichier trop lourd (8 Mo maximum).")

        head = f.read(12)
        f.seek(0)
        is_jpeg = head.startswith(b"\xff\xd8\xff")
        is_png = head.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = head.startswith(b"RIFF") and head[8:12] == b"WEBP"
        is_pdf = head.startswith(b"%PDF-")

        valid = (
            (ext in ("jpg", "jpeg") and is_jpeg)
            or (ext == "png" and is_png)
            or (ext == "webp" and is_webp)
            or (ext == "pdf" and is_pdf)
        )
        if not valid:
            raise forms.ValidationError("Le contenu du fichier ne correspond pas à son format.")
        return f
