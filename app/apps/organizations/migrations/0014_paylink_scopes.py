from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0013_admin_client_verbose_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="paylink_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name="Paylink/оплата включены",
                help_text=(
                    "Если выключить — у этой организации будет скрыта/запрещена оплата (Paylink), "
                    "даже если глобально включено."
                ),
            ),
        ),
        migrations.AddField(
            model_name="doctor",
            name="paylink_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name="Paylink/оплата включены",
                help_text=(
                    "Если выключить — у этого специалиста будет скрыта/запрещена оплата (Paylink), "
                    "даже если у организации и глобально включено."
                ),
            ),
        ),
    ]
