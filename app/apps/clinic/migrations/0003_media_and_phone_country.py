from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0002_rename_clinic_book_doctor__e1b8b8_idx_clinic_book_doctor__105f78_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="specialist",
            name="icon",
            field=models.ImageField(blank=True, null=True, upload_to="specialists/"),
        ),
        migrations.AddField(
            model_name="doctor",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="doctors/"),
        ),
        migrations.CreateModel(
            name="PhoneCountry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=2, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("dial_code", models.CharField(max_length=10)),
                ("flag", models.ImageField(blank=True, null=True, upload_to="phone_countries/")),
            ],
            options={
                "ordering": ["name", "code"],
            },
        ),
    ]