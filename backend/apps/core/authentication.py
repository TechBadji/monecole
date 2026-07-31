"""Authentification JWT adossée aux sessions enregistrées.

Un JWT est autoporteur : le serveur le valide sur sa seule signature, sans rien
consulter. C'est ce qui le rend rapide, et c'est ce qui rend une déconnexion à
distance impossible — un jeton volé reste valide jusqu'à son expiration.

Cette classe raccroche chaque jeton à sa ligne `LoginSession` et refuse ceux
dont la session a été révoquée. Le coût est d'une requête indexée par appel ;
sans elle, « Déconnecter cet appareil » et la fermeture des sessions après un
changement de mot de passe ne seraient que des boutons décoratifs.
"""

from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import LoginSession


class SessionAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        sid = validated_token.get("sid")
        if not sid:
            return user

        session = LoginSession.objects.filter(sid=sid).first()
        # Aucune ligne : jeton émis avant la mise en place des sessions, ou par
        # un chemin qui n'en crée pas. On laisse passer plutôt que de déconnecter
        # tout le monde au déploiement — la révocation ne porte que sur ce
        # qu'elle connaît.
        if session is None:
            return user

        if session.revoked_at is not None:
            raise InvalidToken(
                {
                    "detail": "Cette session a été fermée. Reconnectez-vous.",
                    "code": "session_revoked",
                }
            )

        # `auto_now` sur `last_seen_at` : la sauvegarde suffit à l'horodater.
        # Bornée à la minute pour ne pas écrire à chaque requête d'une page qui
        # en déclenche dix.
        if (timezone.now() - session.last_seen_at).total_seconds() > 60:
            session.save(update_fields=["last_seen_at"])

        return user
