from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from .tenancy import reset_current_tenant, set_current_tenant


class TenantViewSetMixin:
    """Pose le tenant courant une fois l'authentification DRF effectuée.

    `CurrentTenantMiddleware` s'exécute avant l'authentification JWT — à ce moment
    `request.user` est encore anonyme. C'est donc ici, dans `initial()`, que le
    tenant est réellement établi pour les vues d'API.

    **Ne jamais déclarer `queryset = Model.objects...` sur une vue tenant.** Cet
    attribut de classe est évalué à l'import du module, alors qu'aucun tenant n'est
    en contexte : `TenantManager` renvoie `.none()`, et ce `.none()` reste figé pour
    toute la durée du processus — la vue ne retourne alors plus jamais rien, sans la
    moindre erreur. Déclarer `model` (et au besoin `select_related`) à la place : le
    queryset est reconstruit à chaque requête, une fois le tenant connu.
    """

    #: Modèle servi par la vue. Remplace l'attribut `queryset` de DRF.
    model = None
    select_related = ()
    prefetch_related = ()

    def initial(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        self._tenant_token = set_current_tenant(getattr(user, "school", None))
        super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        token = getattr(self, "_tenant_token", None)
        if token is not None:
            reset_current_tenant(token)
            self._tenant_token = None
        return response

    def get_queryset(self):
        if self.model is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} doit déclarer `model` "
                f"ou surcharger `get_queryset()`."
            )
        # Construit à chaque appel : le filtre tenant est appliqué maintenant, pas
        # à l'import du module.
        queryset = self.model.objects.all()
        if self.select_related:
            queryset = queryset.select_related(*self.select_related)
        if self.prefetch_related:
            queryset = queryset.prefetch_related(*self.prefetch_related)
        return queryset

    @property
    def school(self):
        return self.request.user.school

    def current_year(self):
        """Année scolaire visée par la requête.

        Pilotée par `?year=<id>`, sinon l'année marquée courante. Les agrégats
        financiers n'ont aucun sens hors d'une année donnée : mieux vaut une erreur
        explicite qu'un rapport silencieusement vide.
        """
        from .models import SchoolYear

        year_id = self.request.query_params.get("year")
        queryset = SchoolYear.objects.all()
        year = (
            queryset.filter(pk=year_id).first()
            if year_id
            else queryset.filter(is_current=True).first()
        )
        if year is None:
            raise ValidationError(
                {"year": "Aucune année scolaire courante. Précisez ?year=<id> ou définissez-en une."}
            )
        return year


class TenantModelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Base des vues d'API portant des données d'établissement."""

    def perform_create(self, serializer):
        # Rattache d'office la création à l'établissement de l'utilisateur : le
        # client n'a jamais à fournir — ni à pouvoir choisir — le `school`.
        serializer.save(school=self.request.user.school)
