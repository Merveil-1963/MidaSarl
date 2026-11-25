from django.contrib.auth import views as auth
from django.urls import path

from . import views

urlpatterns = [
    path("connexion/", auth.LoginView.as_view(template_name="login.html", redirect_authenticated_user=True), name="login"),
    path("deconnexion/", auth.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("calendrier/", views.calendrier, name="calendrier"),
    path("bons/", views.bons, name="bons"),
    path("bons/nouveau/", views.bon_nouveau, name="bon_nouveau"),
    path("bons/<int:pk>/", views.bon_detail, name="bon_detail"),
    path("bons/<int:pk>/imprimer/", views.bon_imprimer, name="bon_imprimer"),
    path("rapports/", views.rapports, name="rapports"),
    path("kpi/", views.kpi, name="kpi"),
    path("mes-bons/", views.mes_bons, name="mes_bons"),
    path("mes-bons/<int:pk>/", views.mon_bon, name="mon_bon"),
    path("bons/<int:pk>/recu/", views.bon_recu, name="bon_recu"),
    path("api/quota/", views.api_quota, name="api_quota"),
    path("gestion/<str:cle>/", views.liste, name="liste"),
    path("gestion/<str:cle>/nouveau/", views.edition, name="nouveau"),
    path("gestion/<str:cle>/<int:pk>/", views.edition, name="modifier"),
    path("gestion/<str:cle>/<int:pk>/supprimer/", views.suppression, name="supprimer"),
]
