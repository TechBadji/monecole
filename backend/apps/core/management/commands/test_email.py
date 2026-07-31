"""Éprouve la configuration de messagerie de bout en bout.

Le circuit de réinitialisation répond volontairement la même chose que
l'adresse existe ou non, et l'envoi y est silencieux sur échec : sans cette
commande, une configuration SMTP fautive se découvrirait le jour où un
directeur d'établissement n'a rien reçu.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un message de contrôle pour vérifier la configuration SMTP."

    def add_arguments(self, parser):
        parser.add_argument(
            "destinataire",
            help="Adresse à laquelle envoyer le message de contrôle.",
        )

    def handle(self, *args, **options):
        recipient = options["destinataire"]
        console = "console" in settings.EMAIL_BACKEND

        self.stdout.write(f"Backend      : {settings.EMAIL_BACKEND.rsplit('.', 2)[-2]}")
        self.stdout.write(f"Hôte         : {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"Compte       : {settings.EMAIL_HOST_USER or '(aucun)'}")
        self.stdout.write(f"Expéditeur   : {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Base des liens: {settings.PUBLIC_BASE_URL}")

        if console:
            raise CommandError(
                "Les identifiants sont absents : Django écrirait le message sur "
                "cette console au lieu de l'envoyer. Renseignez EMAIL_HOST_USER "
                "et EMAIL_HOST_PASSWORD dans backend/.env — voir "
                "docs/messagerie.md."
            )

        # `fail_silently=False`, à l'inverse du circuit de réinitialisation :
        # ici, on veut précisément voir l'erreur.
        send_mail(
            subject="MonÉcole — message de contrôle",
            message=(
                "Ce message confirme que la configuration SMTP de MonÉcole "
                "fonctionne.\n\nSi vous l'avez trouvé dans les indésirables, "
                "la réinitialisation de mot de passe y arrivera aussi : "
                "voir docs/messagerie.md."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nMessage envoyé à {recipient}. Vérifiez la boîte de réception "
                "**et** les indésirables : un lien de réinitialisation classé "
                "en indésirable est un lien qui n'arrive pas."
            )
        )
