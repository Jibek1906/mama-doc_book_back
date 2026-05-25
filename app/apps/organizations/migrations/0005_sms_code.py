from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_seed_phone_countries"),
    ]

    operations = [
        migrations.CreateModel(
            name="SMSCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(max_length=20)),
                ("code", models.CharField(max_length=6)),
                (
                    "purpose",
                    models.CharField(
                        choices=[("register", "register"), ("reset", "reset"), ("login", "login")],
                        max_length=20,
                    ),
                ),
                ("payload", models.JSONField(blank=True, null=True)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.IntegerField(default=0)),
                ("is_used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="smscode",
            index=models.Index(fields=["phone_number", "purpose", "created_at"], name="sms_phone_purp_created_idx"),
        ),
    ]
