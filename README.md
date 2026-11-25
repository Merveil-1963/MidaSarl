# Gestion du carburant des bus (Django)

## Installation (Windows)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations fuel
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
Ouvrir http://127.0.0.1:8000 (Linux/Mac : `source venv/bin/activate`).

## Les 3 rôles
| Rôle | Ce qu'il fait |
|---|---|
| Administrateur | Crée et valide les bons, consulte les reçus déposés, gère bus, chauffeurs, sites, utilisateurs, rapports. |
| DG | Voit uniquement le tableau de bord KPI (lecture seule). |
| Chauffeur | Voit ses propres bons validés et dépose la photo (ou le PDF) du reçu, liée à son bon. |

Le rôle vient du groupe de l'utilisateur : `Administrateur`, `DG` ou `Chauffeur` (créés automatiquement à la migration).
Un superutilisateur est administrateur. Un compte sans groupe n'a accès à rien.

- Créer un DG : menu Utilisateurs (/admin/), ajouter l'utilisateur, l'affecter au groupe DG.
- Créer un chauffeur avec accès : menu Gestion > Chauffeurs, remplir « Identifiant » et « Mot de passe ».

## Comptes de démonstration (seed_demo)
admin / admin123 · dg / dg123 · andre / andre123 (chauffeur André Mavungu). Changez-les avant toute utilisation réelle.

## Cycle d'un bon
Brouillon > Validé (administrateur) > Servi : le bon est clôturé automatiquement dès que le chauffeur dépose la photo de son reçu.
L'administrateur n'a pas de litres à saisir : les totaux et quotas utilisent les litres du bon.
Un bon peut aussi être Refusé ou Annulé. Les reçus sont dans le dossier `media/recus/` et ne sont accessibles
que par l'administrateur et le chauffeur concerné.

## Mise à jour depuis la version précédente
Copiez les nouveaux fichiers sur les anciens (gardez `db.sqlite3` et `venv`), puis :
```
python manage.py makemigrations fuel
python manage.py migrate
```

## Mise en production
Variables d'environnement SECRET_KEY, DEBUG=0, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS ; `collectstatic` ; gunicorn + nginx ;
PostgreSQL pour plusieurs utilisateurs ; sauvegarder `db.sqlite3` (ou la base) et le dossier `media/`.
