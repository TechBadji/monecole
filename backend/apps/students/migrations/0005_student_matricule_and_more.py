"""Attribue un matricule MXXXX aux élèves existants.

Le remplissage s'intercale **entre** l'ajout de la colonne et la pose de la
contrainte d'unicité : appliquées d'affilée, plusieurs matricules vides
entreraient en collision sur la même école et la migration échouerait.

La numérotation suit l'ordre d'inscription, par établissement — un matricule
accompagne l'élève tout son cursus, il ne doit donc rien devoir au hasard.
"""

from django.db import migrations, models


def assign_matricules(apps, schema_editor):
    Student = apps.get_model("students", "Student")
    School = apps.get_model("core", "School")

    for school_id in School.objects.values_list("id", flat=True):
        students = (
            Student.objects.filter(school_id=school_id, matricule="")
            .order_by("enrollment_date", "created_at", "id")
            .only("id")
        )
        updated = []
        for index, student in enumerate(students, start=1):
            student.matricule = f"M{index:04d}"
            updated.append(student)
        Student.objects.bulk_update(updated, ["matricule"], batch_size=500)


def clear_matricules(apps, schema_editor):
    apps.get_model("students", "Student").objects.update(matricule="")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_user_options'),
        ('students', '0004_backfill_normalized_phones'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='matricule',
            field=models.CharField(default='', editable=False, help_text="Format MXXXX, attribué à l'inscription et conservé pour tout le cursus, même en cas de changement de classe ou de redoublement.", max_length=10, verbose_name='matricule'),
        ),
        migrations.RunPython(assign_matricules, clear_matricules),
        migrations.AddConstraint(
            model_name='student',
            constraint=models.UniqueConstraint(fields=('school', 'matricule'), name='unique_student_matricule_per_school'),
        ),
    ]
