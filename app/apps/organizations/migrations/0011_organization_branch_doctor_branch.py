from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Doctor = apps.get_model("organizations", "Doctor")
    Organization = apps.get_model("organizations", "Organization")
    Branch = apps.get_model("organizations", "Branch")

    org_cache = {}
    branch_cache = {}

    for doc in Doctor.objects.all().only("id", "clinic_name", "clinic_address"):
        name = (doc.clinic_name or "").strip() or "Без организации"
        address = (doc.clinic_address or "").strip()

        org = org_cache.get(name)
        if not org:
            org, _ = Organization.objects.get_or_create(name=name)
            org_cache[name] = org

        key = (org.id, address)
        branch = branch_cache.get(key)
        if not branch:
            branch, _ = Branch.objects.get_or_create(
                organization=org,
                address=address,
                defaults={"title": ""},
            )
            branch_cache[key] = branch

        Doctor.objects.filter(id=doc.id).update(branch=branch)


def backwards(apps, schema_editor):
    Doctor = apps.get_model("organizations", "Doctor")
    Doctor.objects.update(branch=None)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0010_delete_chipwinning"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("address", models.CharField(blank=True, default="", max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="branches",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ["organization__name", "id"], "unique_together": {("organization", "address")}},
        ),
        migrations.AddField(
            model_name="doctor",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="professionals",
                to="organizations.branch",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
