LIBELLES = {"admin": "Administrateur", "dg": "Directeur général", "chauffeur": "Chauffeur"}


def role(user):
    """admin (superuser ou groupe Administrateur), dg, chauffeur, ou None."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return "admin"
    noms = set(user.groups.values_list("name", flat=True))
    for cle, nom in (("admin", "Administrateur"), ("dg", "DG"), ("chauffeur", "Chauffeur")):
        if nom in noms:
            return cle
    return None


def est_admin(user):
    return role(user) == "admin"


def roles(request):
    r = role(request.user)
    return {"role": r, "role_label": LIBELLES.get(r, ""), "est_admin": r == "admin"}
