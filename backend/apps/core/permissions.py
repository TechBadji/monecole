"""Matrice de permissions par rôle.

La matrice est déclarée en Python plutôt qu'en base. Le jeu de rôles est fixe et
défini par le produit : le stocker en base ouvrirait la porte à une élévation de
privilège par écriture de données, et rendrait les permissions non auditables par
revue de code ni testables sans fixture. Elle est ici versionnée, diffable, et
directement couverte par `apps/core/tests/test_permissions.py`.

Si le besoin de rôles personnalisables par établissement apparaît, la structure
migre vers une table `RolePermission` sans changer l'interface `has_perm()`.
"""

from rest_framework.permissions import BasePermission

from .models import Role

VIEW, ADD, CHANGE, DELETE = "view", "add", "change", "delete"
ALL = frozenset({VIEW, ADD, CHANGE, DELETE})
READ = frozenset({VIEW})
WRITE = frozenset({VIEW, ADD, CHANGE})

# Ressource -> rôle -> actions autorisées.
MATRIX = {
    # --- Administration de la plateforme ---------------------------------
    "school": {Role.SUPER_ADMIN: ALL, Role.ADMIN: READ},
    "subscription": {Role.SUPER_ADMIN: ALL, Role.ADMIN: READ},
    "user": {Role.SUPER_ADMIN: ALL, Role.ADMIN: ALL},
    "auditlog": {Role.SUPER_ADMIN: READ, Role.ADMIN: READ, Role.ACCOUNTANT: READ},
    # --- Scolarité --------------------------------------------------------
    "schoolyear": {Role.SUPER_ADMIN: READ, Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: READ},
    "classroom": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: WRITE, Role.TEACHER: READ},
    "family": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: ALL},
    # Le comptable consulte les élèves pour encaisser, mais ne les crée ni ne les
    # supprime — c'est la séparation des tâches exigée par le cahier des charges.
    "student": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: ALL, Role.TEACHER: READ, Role.PARENT: READ},
    "enrollment": {Role.ADMIN: ALL, Role.ACCOUNTANT: WRITE, Role.SECRETARY: ALL, Role.PARENT: READ},
    "discount": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: READ},
    # --- Finances ---------------------------------------------------------
    "monthlypayment": {Role.ADMIN: ALL, Role.ACCOUNTANT: WRITE, Role.SECRETARY: READ, Role.PARENT: READ},
    "expense": {Role.ADMIN: ALL, Role.ACCOUNTANT: WRITE, Role.SECRETARY: READ},
    "expensecategory": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: READ},
    # --- Personnel --------------------------------------------------------
    "teacher": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ, Role.SECRETARY: ALL},
    "salaryrubric": {Role.ADMIN: ALL, Role.ACCOUNTANT: READ},
    "salary": {Role.ADMIN: ALL, Role.ACCOUNTANT: WRITE, Role.SECRETARY: READ},
    # --- Restitution ------------------------------------------------------
    "report": {Role.ADMIN: READ, Role.ACCOUNTANT: READ},
    # --- Migration de données ---------------------------------------------
    "dataimport": {Role.ADMIN: ALL, Role.SECRETARY: WRITE},
}

# Correspondance méthode HTTP -> action.
METHOD_ACTIONS = {
    "GET": VIEW,
    "HEAD": VIEW,
    "OPTIONS": VIEW,
    "POST": ADD,
    "PUT": CHANGE,
    "PATCH": CHANGE,
    "DELETE": DELETE,
}


def has_perm(role, resource, action):
    """Le rôle est-il autorisé à effectuer `action` sur `resource` ?"""
    return action in MATRIX.get(resource, {}).get(role, frozenset())


class RoleBasedPermission(BasePermission):
    """Applique `MATRIX` à partir de l'attribut `resource` de la vue.

    Une vue sans `resource` déclarée est refusée : sur une application financière,
    l'oubli doit fermer l'accès, pas l'ouvrir.
    """

    message = "Votre rôle ne vous autorise pas cette opération."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        resource = getattr(view, "resource", None)
        if resource is None:
            return False

        action = METHOD_ACTIONS.get(request.method)
        if action is None:
            return False

        return has_perm(user.role, resource, action)
