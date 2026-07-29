"""Écriture du journal d'audit."""

from django.forms.models import model_to_dict

from .models import AuditLog

# Champs jamais recopiés dans le journal.
SENSITIVE_FIELDS = {"password", "cni"}


def snapshot(instance):
    """Représentation sérialisable d'une instance, hors champs sensibles."""
    if instance is None:
        return None
    data = model_to_dict(instance)
    return {
        key: (str(value) if not isinstance(value, (int, float, bool, type(None))) else value)
        for key, value in data.items()
        if key not in SENSITIVE_FIELDS
    }


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def user_label(user):
    """Identité figée de l'auteur d'une opération.

    Contient l'email et non le seul nom d'affichage : le nom peut changer, n'est pas
    unique, et le compte peut être supprimé — la clé étrangère `user` passe alors à
    NULL. Sans email dans le libellé, la trace ne désigne plus personne.
    """
    if user is None:
        return "anonyme"
    full_name = user.get_full_name()
    return f"{full_name} <{user.email}>" if full_name else user.email


def record(request, action, instance, before=None, after=None):
    """Consigne une opération.

    `before`/`after` sont calculés par l'appelant lorsqu'il dispose des deux états
    (cas d'une modification) ; sinon ils sont dérivés de `instance`.
    """
    user = getattr(request, "user", None)
    user = user if getattr(user, "is_authenticated", False) else None

    AuditLog.objects.create(
        school=getattr(instance, "school", None) or getattr(user, "school", None),
        user=user,
        user_label=user_label(user),
        action=action,
        entity=instance.__class__.__name__,
        entity_id=str(getattr(instance, "pk", "") or ""),
        before=before,
        after=after if after is not None else snapshot(instance),
        ip_address=client_ip(request),
    )


class AuditedModelViewSetMixin:
    """Consigne automatiquement les créations, modifications et suppressions.

    À appliquer aux vues portant des données financières : paiements, dépenses,
    salaires. Le cahier des charges l'exige et le critère d'acceptation le vérifie.
    """

    def perform_create(self, serializer):
        instance = serializer.save()
        record(self.request, AuditLog.Action.CREATE, instance)

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        instance = serializer.save()
        record(self.request, AuditLog.Action.UPDATE, instance, before=before, after=snapshot(instance))

    def perform_destroy(self, instance):
        before = snapshot(instance)
        # L'entrée d'audit est écrite avant la suppression : après, la clé primaire
        # et les relations ne sont plus lisibles.
        record(self.request, AuditLog.Action.DELETE, instance, before=before, after=None)
        instance.delete()
