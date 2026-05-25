from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0023_remove_review_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="organizations/logos/"),
        ),
        migrations.AddField(
            model_name="branch",
            name="specialists",
            field=models.ManyToManyField(blank=True, related_name="branches", to="organizations.specialist"),
        ),
        migrations.CreateModel(
            name="BranchSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "day_of_week",
                    models.IntegerField(
                        choices=[
                            (0, "Пн"),
                            (1, "Вт"),
                            (2, "Ср"),
                            (3, "Чт"),
                            (4, "Пт"),
                            (5, "Сб"),
                            (6, "Вс"),
                        ]
                    ),
                ),
                ("start_time", models.TimeField(blank=True, null=True)),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("break_start", models.TimeField(blank=True, null=True)),
                ("break_end", models.TimeField(blank=True, null=True)),
                ("is_working", models.BooleanField(default=True)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="schedule",
                        to="organizations.branch",
                    ),
                ),
            ],
            options={
                "verbose_name": "График филиала",
                "verbose_name_plural": "Графики филиалов",
                "unique_together": {("branch", "day_of_week")},
            },
        ),
    ]
