from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0022_review_image_and_patient_inn_int"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="review",
            name="image",
        ),
    ]
