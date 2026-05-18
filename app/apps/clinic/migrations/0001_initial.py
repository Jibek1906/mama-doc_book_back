from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Specialist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("icon_url", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="Doctor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=200)),
                ("photo_url", models.CharField(blank=True, max_length=255)),
                ("rating", models.DecimalField(decimal_places=1, default=0.0, max_digits=2)),
                ("rating_count", models.IntegerField(default=0)),
                ("experience_years", models.IntegerField(default=0)),
                ("bio", models.TextField(blank=True)),
                ("education", models.TextField(blank=True)),
                ("clinic_address", models.CharField(blank=True, max_length=255)),
                ("clinic_name", models.CharField(blank=True, max_length=200)),
                ("phone_admin", models.CharField(blank=True, max_length=20)),
                ("slot_duration_min", models.IntegerField(default=30)),
                (
                    "consultation_type",
                    models.CharField(
                        choices=[("offline", "offline"), ("online", "online"), ("both", "both")],
                        default="offline",
                        max_length=20,
                    ),
                ),
                (
                    "gender",
                    models.CharField(
                        choices=[("male", "male"), ("female", "female")],
                        default="female",
                        max_length=10,
                    ),
                ),
                ("languages", models.CharField(default="ru", max_length=100)),
                ("is_active", models.BooleanField(default=True)),
                ("is_accepting_new", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "primary_specialist",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="primary_doctors",
                        to="clinic.specialist",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DoctorSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day_of_week", models.IntegerField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("break_start", models.TimeField(blank=True, null=True)),
                ("break_end", models.TimeField(blank=True, null=True)),
                ("is_working", models.BooleanField(default=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule",
                        to="clinic.doctor",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DoctorSpecialty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="doctor_specialties",
                        to="clinic.doctor",
                    ),
                ),
                (
                    "specialist",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="clinic.specialist"),
                ),
            ],
            options={
                "unique_together": {("doctor", "specialist")},
            },
        ),
        migrations.CreateModel(
            name="OTPCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=20)),
                ("code", models.CharField(max_length=6)),
                ("expires_at", models.DateTimeField()),
                ("is_used", models.BooleanField(default=False)),
                ("attempts", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Patient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=20, unique=True)),
                ("full_name", models.CharField(blank=True, max_length=200)),
                ("birth_date", models.DateField(blank=True, null=True)),
                ("gender", models.CharField(blank=True, max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ScheduleException",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("is_day_off", models.BooleanField(default=True)),
                ("reason", models.CharField(blank=True, max_length=200)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedule_exceptions",
                        to="clinic.doctor",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("price", models.IntegerField()),
                ("duration_min", models.IntegerField(default=30)),
                ("description", models.TextField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.IntegerField(default=0)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="services",
                        to="clinic.doctor",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="Booking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("booking_date", models.DateField()),
                ("booking_time", models.TimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("confirmed", "confirmed"),
                            ("cancelled", "cancelled"),
                            ("completed", "completed"),
                            ("no_show", "no_show"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("confirmation_code", models.CharField(max_length=10, unique=True)),
                ("total_price", models.IntegerField(null=True)),
                ("total_duration_min", models.IntegerField(default=30)),
                ("cancellation_reason", models.CharField(blank=True, max_length=255)),
                ("cancelled_by", models.CharField(blank=True, max_length=20)),
                ("reminder_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bookings",
                        to="clinic.doctor",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bookings",
                        to="clinic.patient",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BookingService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.IntegerField()),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="booking_services",
                        to="clinic.booking",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="clinic.service"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Review",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("patient_avatar", models.CharField(blank=True, max_length=255)),
                ("rating", models.IntegerField()),
                ("text", models.TextField(blank=True)),
                ("is_approved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="clinic.booking"),
                ),
                (
                    "doctor",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="clinic.doctor"),
                ),
                (
                    "patient",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="clinic.patient"),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="otpcode",
            index=models.Index(fields=["phone", "created_at"], name="clinic_otp_phone_0b5f2c_idx"),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["doctor", "booking_date", "booking_time"], name="clinic_book_doctor__e1b8b8_idx"),
        ),
    ]
