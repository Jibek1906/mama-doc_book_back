from django.db import migrations


def seed_phone_countries(apps, schema_editor):
    PhoneCountry = apps.get_model("organizations", "PhoneCountry")

    # Минимальный набор для фронта (как в текущем UI)
    PhoneCountry.objects.update_or_create(
        code="KG",
        defaults={"name": "Кыргызстан", "dial_code": "+996"},
    )
    PhoneCountry.objects.update_or_create(
        code="RU",
        defaults={"name": "Россия", "dial_code": "+7"},
    )
    PhoneCountry.objects.update_or_create(
        code="KZ",
        defaults={"name": "Казахстан", "dial_code": "+7"},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0003_media_and_phone_country"),
    ]

    operations = [
        migrations.RunPython(seed_phone_countries, migrations.RunPython.noop),
    ]
