"""Isolation multi-tenant.

Stratégie retenue : *shared database, shared schema* — une colonne `school_id` sur
chaque table métier, plus un filtrage automatique.

Le filtrage n'est pas laissé à la discrétion de l'appelant : le manager par défaut de
tout modèle `TenantScopedModel` applique le filtre à partir du tenant courant, stocké
dans un contexte de thread posé par `CurrentTenantMiddleware`. Une vue qui oublierait
de filtrer ne fuite donc pas — elle ne voit rien.

Deux échappatoires explicites, volontairement verbeuses pour être repérables en revue :
    Model.objects.all_tenants()        -> lève le filtre (super-admin, tâches système)
    with tenant_context(school): ...   -> impose un tenant (tests, commandes, imports)
"""

import contextlib
import contextvars

from django.db import models

# Le tenant courant. `contextvars` plutôt que `threading.local` : le contexte suit
# correctement les coroutines si l'application passe en ASGI.
_current_tenant = contextvars.ContextVar("current_tenant", default=None)

# Interrupteur du filtrage, utilisé par `all_tenants()`.
_unscoped = contextvars.ContextVar("unscoped", default=False)


def get_current_tenant():
    """Retourne l'établissement courant, ou None hors requête authentifiée."""
    return _current_tenant.get()


def set_current_tenant(school):
    """Pose le tenant courant. Retourne le jeton de réinitialisation."""
    return _current_tenant.set(school)


def reset_current_tenant(token):
    _current_tenant.reset(token)


@contextlib.contextmanager
def tenant_context(school):
    """Force un tenant sur la durée du bloc.

    Destiné aux exécutions hors cycle requête/réponse : commandes de gestion,
    imports, tests. En vue applicative, le middleware s'en charge.
    """
    token = _current_tenant.set(school)
    try:
        yield school
    finally:
        _current_tenant.reset(token)


@contextlib.contextmanager
def unscoped():
    """Lève le filtrage tenant sur la durée du bloc.

    À n'utiliser que pour des opérations légitimement transverses (statistiques
    d'usage de la plateforme, migrations de données). Tout appel doit être justifié.
    """
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)


class TenantQuerySet(models.QuerySet):
    def all_tenants(self):
        """Retourne le queryset sans filtrage tenant."""
        return self.model._base_manager.get_queryset()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager filtrant systématiquement sur le tenant courant."""

    def get_queryset(self):
        qs = super().get_queryset()
        if _unscoped.get():
            return qs
        tenant = get_current_tenant()
        if tenant is None:
            # Aucun tenant en contexte : on ne devine pas, on ne montre rien.
            # C'est le cas d'un appel non authentifié ou d'un oubli de contexte —
            # dans les deux cas, l'ensemble vide est la réponse sûre.
            return qs.none()
        return qs.filter(school=tenant)


class TenantScopedModel(models.Model):
    """Base de tout modèle appartenant à un établissement.

    `objects` filtre sur le tenant courant. `all_objects` ne filtre pas et sert
    aux accès système ; ne pas l'utiliser dans une vue exposée.
    """

    school = models.ForeignKey(
        "core.School",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name="établissement",
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Renseigne le tenant depuis le contexte si l'appelant ne l'a pas fait,
        # et refuse toute écriture croisée vers un autre établissement.
        tenant = get_current_tenant()
        if self.school_id is None and tenant is not None:
            self.school = tenant
        if tenant is not None and self.school_id != tenant.pk:
            raise PermissionError(
                f"Écriture inter-établissement refusée : {self.__class__.__name__} "
                f"vers l'établissement {self.school_id} depuis le contexte {tenant.pk}."
            )
        return super().save(*args, **kwargs)
