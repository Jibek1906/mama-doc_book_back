from datetime import datetime, time, timedelta
import random

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def fill_review_bookings(apps, schema_editor):
    Review = apps.get_model("organizations", "Review")
    Booking = apps.get_model("organizations", "Booking")

    base_date = timezone.localdate()
    idx = 0
    for review in Review.objects.filter(booking__isnull=True).select_related("doctor", "patient"):
        doctor = review.doctor
        patient = review.patient
        slot_minutes = getattr(doctor, "slot_duration_min", 30) or 30
        booking_time = (
            datetime.combine(base_date, time(9, 0))
            + timedelta(minutes=idx * slot_minutes)
        ).time()

        confirmation_code = None
        for _ in range(20):
            code = f"TG{random.randint(10000, 99999)}"
            if not Booking.objects.filter(confirmation_code=code).exists():
                confirmation_code = code
                break
        if confirmation_code is None:
            confirmation_code = f"TG{random.randint(10000, 99999)}"

        booking = Booking.objects.create(
            doctor=doctor,
            patient=patient,
            booking_date=base_date,
            booking_time=booking_time,
            status="completed",
            confirmation_code=confirmation_code,
            total_price=0,
            total_duration_min=slot_minutes,
        )
        review.booking = booking
        review.save()
        idx += 1


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("organizations", "0007_alter_doctor_photo_url_alter_specialist_icon_url"),
    ]

    operations = [
        migrations.RunPython(fill_review_bookings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="review",
            name="booking",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="organizations.booking",
            ),
        ),
    ]