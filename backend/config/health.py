"""Point de santé, interrogé par Docker et par le frontal.

Il vérifie la base : un conteneur qui répond « ok » sans savoir joindre
PostgreSQL serait déclaré sain et recevrait du trafic qu'il ne peut pas servir.

Volontairement hors de `/api/` : ce n'est pas une ressource métier, il n'exige
aucune authentification, et il doit rester joignable même si l'API est en
défaut.
"""

from django.db import connection
from django.http import JsonResponse


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as error:  # noqa: BLE001 — on veut le signaler, pas le typer
        return JsonResponse(
            {"status": "degraded", "database": str(error)[:200]}, status=503
        )
    return JsonResponse({"status": "ok", "database": "ok"})
