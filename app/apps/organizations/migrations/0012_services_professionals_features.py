from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_service_links(apps, schema_editor):
    Service = apps.get_model("organizations", "Service")
    ProfessionalService = apps.get_model("organizations", "ProfessionalService")

    links = []
    for service in Service.objects.exclude(doctor_id__isnull=True).only("id", "doctor_id"):
        links.append(
            ProfessionalService(
                professional_id=service.doctor_id,
                service_id=service.id,
                is_active=True,
            )
        )
    ProfessionalService.objects.bulk_create(links, ignore_conflicts=True)


def remove_copied_service_links(apps, schema_editor):
    ProfessionalService = apps.get_model("organizations", "ProfessionalService")
    ProfessionalService.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0011_organization_branch_doctor_branch"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="branch",
            options={
                "ordering": ["organization__name", "id"],
                "verbose_name": "Филиал",
                "verbose_name_plural": "Филиалы",
            },
        ),
        migrations.AlterModelOptions(
            name="doctor",
            options={
                "verbose_name": "Специалист",
                "verbose_name_plural": "Специалисты",
            },
        ),
        migrations.AlterModelOptions(
            name="doctorspecialty",
            options={
                "verbose_name": "Специализация специалиста",
                "verbose_name_plural": "Специализации специалистов",
            },
        ),
        migrations.AlterModelOptions(
            name="organization",
            options={
                "ordering": ["name", "id"],
                "verbose_name": "Организация",
                "verbose_name_plural": "Организации",
            },
        ),
        migrations.AlterModelOptions(
            name="service",
            options={
                "ordering": ["sort_order", "id"],
                "verbose_name": "Услуга",
                "verbose_name_plural": "Услуги",
            },
        ),
        migrations.AlterModelOptions(
            name="specialist",
            options={
                "ordering": ["sort_order", "id"],
                "verbose_name": "Специализация",
                "verbose_name_plural": "Специализации",
            },
        ),
        migrations.AlterField(
            model_name="service",
            name="doctor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legacy_services",
                to="organizations.doctor",
            ),
        ),
        migrations.CreateModel(
            name="ProjectFeatureSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("branches_enabled", models.BooleanField(default=True)),
                ("paylink_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Настройки функций",
                "verbose_name_plural": "Настройки функций",
            },
        ),
        migrations.CreateModel(
            name="ProfessionalService",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "professional",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="professional_services",
                        to="organizations.doctor",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="professional_services",
                        to="organizations.service",
                    ),
                ),
            ],
            options={
                "verbose_name": "Услуга специалиста",
                "verbose_name_plural": "Услуги специалистов",
                "unique_together": {("professional", "service")},
            },
        ),
        migrations.AddField(
            model_name="service",
            name="professionals",
            field=models.ManyToManyField(
                blank=True,
                related_name="services",
                through="organizations.ProfessionalService",
                to="organizations.doctor",
            ),
        ),
        migrations.RunPython(copy_legacy_service_links, remove_copied_service_links),
    ]
