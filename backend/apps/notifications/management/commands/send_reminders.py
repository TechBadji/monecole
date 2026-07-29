"""Campagne de rappels de paiement, destinée à un ordonnanceur.

    # Prévisualisation, aucun envoi
    python manage.py send_reminders --dry-run

    # Envoi réel, arriérés d'au moins 20 000 FCFA
    python manage.py send_reminders --min-amount 20000

Exemple de planification, le 5 de chaque mois à 9 h :

    0 9 5 * *  cd /srv/monecole/backend && .venv/bin/python manage.py send_reminders

Idempotent à la journée : relancer la commande le même jour n'envoie rien de plus.
C'est ce qui rend une planification sûre — un `cron` qui double, un serveur qui
redémarre, une exécution manuelle de contrôle ne coûtent pas un second SMS à
plusieurs centaines de parents.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import School, SchoolYear
from apps.core.tenancy import tenant_context, unscoped
from apps.notifications.services import run_arrears_reminders
from apps.notifications.sms import send_sms
from django.conf import settings


class Command(BaseCommand):
    help = "Envoie les rappels d'arriérés de scolarité aux parents, par SMS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", help="Slug d'un établissement. Par défaut : tous les actifs."
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche les messages sans les envoyer.",
        )
        parser.add_argument(
            "--min-amount", type=int, default=0,
            help="Seuil d'arriéré en dessous duquel on ne relance pas.",
        )

    def handle(self, *args, **options):
        configured = bool(settings.LAM_ACCESS_KEY and settings.LAM_ACCESS_PASSWORD)
        if not configured and not options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    "LaFricaMobile n'est pas configuré : les envois seront simulés."
                )
            )

        with unscoped():
            schools = School.objects.filter(is_active=True)
            if options["school"]:
                schools = schools.filter(slug=options["school"])
                if not schools.exists():
                    raise CommandError(f"Établissement « {options['school']} » introuvable.")
            schools = list(schools)

        for school in schools:
            with tenant_context(school):
                year = SchoolYear.objects.filter(is_current=True).first()
                if year is None:
                    self.stdout.write(
                        self.style.WARNING(f"{school.name} : aucune année courante, ignoré.")
                    )
                    continue

                result = run_arrears_reminders(
                    school,
                    year,
                    triggered_by="commande planifiée",
                    dry_run=options["dry_run"],
                    min_amount=options["min_amount"],
                )

            self._report(school, result, options["dry_run"])

    def _report(self, school, result, dry_run):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {school.name}"))

        if dry_run:
            self.stdout.write(f"    à relancer ......... {result['would_send']}")
            self.stdout.write(f"    sans numéro ........ {result['skipped']}")
            for entry in result["preview"][:5]:
                self.stdout.write(f"      {entry['phone']}  {entry['message'][:70]}…")
            if result["would_send"] > 5:
                self.stdout.write(f"      … et {result['would_send'] - 5} autres")
            return

        if result.get("already_run"):
            self.stdout.write("    campagne déjà exécutée aujourd'hui — rien envoyé.")
            return

        self.stdout.write(f"    envoyés ............ {result['sent']}")
        self.stdout.write(f"    échecs ............. {result['failed']}")
        self.stdout.write(f"    sans numéro ........ {result['skipped']}")
        if result.get("simulated"):
            self.stdout.write(
                self.style.WARNING("    mode simulation : aucun SMS réellement émis.")
            )
