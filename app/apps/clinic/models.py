from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from api.v1.utils import label_for_day, time_range


class Specialist(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon_url = models.ImageField(upload_to="specialists/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.title


class Doctor(models.Model):
    CONSULTATION_CHOICES = [
        ("offline", "offline"),
        ("online", "online"),
        ("both", "both"),
    ]
    GENDER_CHOICES = [("male", "male"), ("female", "female")]

    full_name = models.CharField(max_length=200)
    photo_url = models.ImageField(upload_to="doctors/", blank=True, null=True)

    primary_specialist = models.ForeignKey(
        Specialist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_doctors",
    )

    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0.0)
    rating_count = models.IntegerField(default=0)
    experience_years = models.IntegerField(default=0)
    bio = models.TextField(blank=True)
    education = models.TextField(blank=True)

    clinic_address = models.CharField(max_length=255, blank=True)
    clinic_name = models.CharField(max_length=200, blank=True)
    phone_admin = models.CharField(max_length=20, blank=True)

    slot_duration_min = models.IntegerField(default=30)
    consultation_type = models.CharField(
        max_length=20, choices=CONSULTATION_CHOICES, default="offline"
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="female")
    languages = models.CharField(max_length=100, default="ru")

    is_active = models.BooleanField(default=True)
    is_accepting_new = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.full_name

    def get_calendar(self, days: int = 30):
        today = timezone.localtime(timezone.now()).date()
        result = []
        for i in range(days):
            d = today + timedelta(days=i)
            times = self._get_free_slots_for_date(d)
            result.append(
                {
                    "date": d.isoformat(),
                    "label": label_for_day(d),
                    "is_available": len(times) > 0,
                    "slots_count": len(times),
                    "times": times,
                }
            )
        return result

    def get_first_available_day(self, days: int = 30):
        for day in self.get_calendar(days=days):
            if day["is_available"]:
                return {
                    "date": timezone.datetime.fromisoformat(day["date"]).date(),
                    "times": day["times"],
                }
        return None

    def _get_free_slots_for_date(self, d):
        exc = self.schedule_exceptions.filter(date=d).first()
        if exc and exc.is_day_off:
            return []

        dow = d.weekday()  # 0=Mon
        schedule = self.schedule.filter(day_of_week=dow, is_working=True).first()
        if not schedule:
            return []

        all_slots = []
        for t in time_range(schedule.start_time, schedule.end_time, self.slot_duration_min):
            if schedule.break_start and schedule.break_end:
                if schedule.break_start <= t < schedule.break_end:
                    continue
            all_slots.append(t.strftime("%H:%M"))

        booked = set(
            self.bookings.filter(booking_date=d)
            .exclude(status="cancelled")
            .values_list("booking_time", flat=True)
        )
        booked_str = {bt.strftime("%H:%M") for bt in booked}
        return [t for t in all_slots if t not in booked_str]


class DoctorSpecialty(models.Model):
    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="doctor_specialties"
    )
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("doctor", "specialist")


class Service(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    duration_min = models.IntegerField(default=30)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class DoctorSchedule(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="schedule")
    day_of_week = models.IntegerField()  # 0=Mon
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    is_working = models.BooleanField(default=True)


class ScheduleException(models.Model):
    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="schedule_exceptions"
    )
    date = models.DateField()
    is_day_off = models.BooleanField(default=True)
    reason = models.CharField(max_length=200, blank=True)


class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)


class OTPCode(models.Model):
    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["phone", "created_at"])]


class SMSCode(models.Model):
    PURPOSE_REGISTER = "register"
    PURPOSE_RESET = "reset"
    PURPOSE_LOGIN = "login"

    PURPOSE_CHOICES = [
        (PURPOSE_REGISTER, PURPOSE_REGISTER),
        (PURPOSE_RESET, PURPOSE_RESET),
        (PURPOSE_LOGIN, PURPOSE_LOGIN),
    ]

    phone_number = models.CharField(max_length=20)
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    payload = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["phone_number", "purpose", "created_at"],
                name="sms_phone_purp_created_idx",
            ),
        ]


class Booking(models.Model):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("confirmed", "confirmed"),
        ("cancelled", "cancelled"),
        ("completed", "completed"),
        ("no_show", "no_show"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="bookings")
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="bookings")
    booking_date = models.DateField()
    booking_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    confirmation_code = models.CharField(max_length=10, unique=True)
    total_price = models.IntegerField(null=True)
    total_duration_min = models.IntegerField(default=30)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    cancelled_by = models.CharField(max_length=20, blank=True)
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["doctor", "booking_date", "booking_time"])]

    def set_services(self, services):
        BookingService.objects.filter(booking=self).delete()
        for svc in services:
            BookingService.objects.create(booking=self, service=svc, price=svc.price)


class BookingService(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="booking_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    price = models.IntegerField()


class Review(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="reviews")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="reviews")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True)
    patient_avatar = models.CharField(max_length=255, blank=True)
    rating = models.IntegerField()
    text = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class PhoneCountry(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100)
    dial_code = models.CharField(max_length=10)
    flag = models.ImageField(upload_to="phone_countries/", blank=True, null=True)

    class Meta:
        ordering = ["name", "code"]

    def __str__(self) -> str:
        return f"{self.name} ({self.dial_code})"
