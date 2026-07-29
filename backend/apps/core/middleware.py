from .tenancy import reset_current_tenant, set_current_tenant


class CurrentTenantMiddleware:
    """Pose le tenant courant à partir de l'utilisateur authentifié.

    Le tenant provient **exclusivement** de l'utilisateur en base — jamais d'un
    en-tête, d'un paramètre de requête ou d'un sous-domaine fourni par le client.
    C'est ce qui rend l'isolation non contournable : un attaquant porteur d'un jeton
    valide de l'école A ne dispose d'aucun levier pour se faire passer pour l'école B.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # L'authentification DRF (JWT) intervient au niveau de la vue, donc après ce
        # middleware. On pose ici ce qui est disponible pour les vues à session
        # (l'admin Django) ; DRF repasse ensuite par `TenantAPIViewMixin`.
        school = getattr(getattr(request, "user", None), "school", None)
        token = set_current_tenant(school)
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant(token)
        return response
