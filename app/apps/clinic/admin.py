from django.contrib import admin

from .models import (
    Booking,
    BookingService,
    Doctor,
    DoctorSchedule,
    DoctorSpecialty,
    OTPCode,
    Patient,
    PhoneCountry,
    Review,
    SMSCode,
    ScheduleException,
    Service,
    Specialist,
)


@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("title", "slug")




class DoctorSpecialtyInline(admin.TabularInline):
    model = DoctorSpecialty
    extra = 0


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0


class DoctorScheduleInline(admin.TabularInline):
    model = DoctorSchedule
    extra = 0


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "primary_specialist", "rating", "is_active")
    list_filter = ("is_active", "primary_specialist")
    search_fields = ("full_name",)
    inlines = [DoctorSpecialtyInline, ServiceInline, DoctorScheduleInline]




@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "phone", "full_name", "created_at")
    search_fields = ("phone", "full_name")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "phone",
        "code",
        "expires_at",
        "is_used",
        "attempts",
        "created_at",
    )
    list_filter = ("is_used",)
    search_fields = ("phone",)


@admin.register(SMSCode)
class SMSCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "phone_number",
        "purpose",
        "code",
        "expires_at",
        "is_used",
        "attempts",
        "created_at",
    )
    list_filter = ("purpose", "is_used")
    search_fields = ("phone_number",)


class BookingServiceInline(admin.TabularInline):
    model = BookingService
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "doctor", "patient", "booking_date", "booking_time", "status")
    list_filter = ("status", "booking_date")
    inlines = [BookingServiceInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "doctor", "patient", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")


admin.site.register(ScheduleException)


@admin.register(PhoneCountry)
class PhoneCountryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "dial_code")
    search_fields = ("code", "name", "dial_code")
