"""Renseigne les téléphones normalisés des enregistrements existants.

Sans ce remplissage, aucun parent déjà en base ne pourrait se connecter au portail :
le rapprochement numéro → enfants s'appuie exclusivement sur ces colonnes.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from apps.notifications.sms import normalize_phone

    Student = apps.get_model("students", "Student")
    Family = apps.get_model("students", "Family")

    students = []
    for student in Student.objects.exclude(parent_phone="").only("id", "parent_phone"):
        student.parent_phone_e164 = normalize_phone(student.parent_phone)
        students.append(student)
    Student.objects.bulk_update(students, ["parent_phone_e164"], batch_size=500)

    families = []
    for family in Family.objects.exclude(phone="").only("id", "phone"):
        family.phone_e164 = normalize_phone(family.phone)
        families.append(family)
    Family.objects.bulk_update(families, ["phone_e164"], batch_size=500)


def backwards(apps, schema_editor):
    # Colonnes purement dérivées : les vider est sans perte, elles se reconstruisent.
    apps.get_model("students", "Student").objects.update(parent_phone_e164="")
    apps.get_model("students", "Family").objects.update(phone_e164="")


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0003_family_phone_e164_student_parent_phone_e164"),
        ("notifications", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
