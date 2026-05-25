from django.db import migrations, models


def normalize_patient_inn(apps, schema_editor):
    """Convert legacy Patient.inn values to something BigIntegerField can handle.

    Previously `inn` was CharField with default "".
    During migration Postgres fails on casting "" -> bigint.
    """

    Patient = apps.get_model("organizations", "Patient")

    for p in Patient.objects.all().only("id", "inn").iterator():
        raw = p.inn
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            Patient.objects.filter(id=p.id).update(inn=None)
            continue

        # keep only digits (defensive)
        digits = "".join(ch for ch in s if ch.isdigit())

        if digits:
            try:
                Patient.objects.filter(id=p.id).update(inn=digits)
            except Exception:
                Patient.objects.filter(id=p.id).update(inn=None)
        else:
            # If there are any non-digit values in DB, they cannot be converted.
            Patient.objects.filter(id=p.id).update(inn=None)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0021_alter_doctorspecialty_specialist"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="reviews/"),
        ),
        # Step 1: make column nullable while it is still CharField so we can safely set NULLs.
        migrations.AlterField(
            model_name="patient",
            name="inn",
            field=models.CharField(blank=True, default="", max_length=32, null=True),
        ),
        migrations.RunPython(normalize_patient_inn, migrations.RunPython.noop),
        # Step 2: change type to bigint (Postgres will cast remaining digit-strings -> bigint)
        migrations.AlterField(
            model_name="patient",
            name="inn",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]