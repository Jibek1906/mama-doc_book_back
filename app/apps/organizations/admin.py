from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Booking,
    BookingService,
    Professional,
    Branch,
    BranchSchedule,
    ProfessionalSchedule,
    ProfessionalSpecialty,
    OTPCode,
    Client,
    PhoneCountry,
    ProfessionalService,
    ProjectFeatureSettings,
    Review,
    SMSCode,
    ScheduleException,
    Service,
    Specialist,
    Organization,
    ProfessionalAccount,
    PendingClientProfile,
)


@admin.register(Specialist)
class SpecialistAdmin(ModelAdmin):
    list_display = ("id", "title", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("title", "slug")
    ordering = ("sort_order", "id")


class BranchInline(TabularInline):
    model = Branch
    extra = 0


class BranchScheduleInline(TabularInline):
    model = BranchSchedule
    extra = 0


class ProfessionalSpecialtyInline(TabularInline):
    model = ProfessionalSpecialty
    extra = 0


class ProfessionalServiceInline(TabularInline):
    model = ProfessionalService
    extra = 0
    fk_name = "professional"


class ProfessionalScheduleInline(TabularInline):
    model = ProfessionalSchedule
    extra = 0


class ProfessionalAccountInlineForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Пароль для входа врача (username+password).",
    )

    class Meta:
        model = ProfessionalAccount
        fields = ("phone", "username", "password")

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Обязательное поле")

        existing = User.objects.filter(username=username)
        if self.instance and getattr(self.instance, "user_id", None):
            existing = existing.exclude(id=self.instance.user_id)
        if existing.exists():
            raise forms.ValidationError("Такой username уже используется")
        return username

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get("password")

        if instance.user_id:
            user = instance.user
            user.username = instance.username
            if password:
                user.set_password(password)
            user.save()
        else:
            user = User(username=instance.username)
            user.set_password(password or "default123")
            user.save()
            instance.user = user

        if commit:
            instance.save()
        return instance


class ProfessionalAccountInline(admin.StackedInline):
    model = ProfessionalAccount
    form = ProfessionalAccountInlineForm
    can_delete = False
    max_num = 1


@admin.register(Professional)
class ProfessionalAdmin(ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "primary_specialist",
        "is_active",
        "paylink_enabled",
        "rating",
        "created_at",
    )
    list_filter = ("is_active", "primary_specialist")
    search_fields = ("full_name",)
    filter_horizontal = ("branches",)
    inlines = [ProfessionalAccountInline, ProfessionalSpecialtyInline, ProfessionalServiceInline, ProfessionalScheduleInline]
    ordering = ("id",)


class ServiceProfessionalInline(TabularInline):
    model = ProfessionalService
    extra = 0
    fk_name = "service"


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("id", "name", "price", "duration_min", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    inlines = [ServiceProfessionalInline]
    ordering = ("sort_order", "id")


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ("id", "name", "paylink_enabled", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [BranchInline]
    # Keep stable numeric ordering by default (like in other lists)
    ordering = ("id",)


@admin.register(Branch)
class BranchAdmin(ModelAdmin):
    list_display = ("id", "organization", "address", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("address", "organization__name")
    ordering = ("id",)
    filter_horizontal = ("specialists",)
    inlines = [BranchScheduleInline]


@admin.register(ProjectFeatureSettings)
class ProjectFeatureSettingsAdmin(ModelAdmin):
    list_display = ("id", "branches_enabled", "paylink_enabled", "updated_at")

    def has_add_permission(self, request):
        return not ProjectFeatureSettings.objects.exists()


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = (
        "id",
        "phone",
        "full_name",
        "inn",
        "birth_date",
        "gender",
        "created_at",
    )
    search_fields = ("phone", "full_name", "inn", "nickname")
    ordering = ("id",)


@admin.register(PendingClientProfile)
class PendingClientProfileAdmin(ModelAdmin):
    list_display = ("id", "phone", "token", "expires_at", "is_used", "created_at")
    list_filter = ("is_used",)
    search_fields = ("phone", "token")
    ordering = ("-created_at",)


@admin.register(OTPCode)
class OTPCodeAdmin(ModelAdmin):
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
    ordering = ("id",)


@admin.register(SMSCode)
class SMSCodeAdmin(ModelAdmin):
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
    ordering = ("id",)


class BookingServiceInline(TabularInline):
    model = BookingService
    extra = 0


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = ("id", "professional", "client", "booking_date", "booking_time", "status")
    list_filter = ("status", "booking_date")
    inlines = [BookingServiceInline]
    ordering = ("id",)

    @admin.display(description="Клиент")
    def client_display(self, obj):
        return obj.client


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ("id", "professional", "client", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")
    ordering = ("id",)

    @admin.display(description="Клиент")
    def client_display(self, obj):
        return obj.client


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(ModelAdmin):
    list_display = ("id", "professional", "date", "is_day_off", "reason")
    list_filter = ("is_day_off", "date")
    ordering = ("id",)


@admin.register(PhoneCountry)
class PhoneCountryAdmin(ModelAdmin):
    list_display = ("code", "name", "dial_code")
    search_fields = ("code", "name", "dial_code")
    ordering = ("name", "code")


from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    pass


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(ProfessionalAccount)
class ProfessionalAccountAdmin(ModelAdmin):
    class ProfessionalAccountForm(forms.ModelForm):
        password = forms.CharField(
            required=False,
            widget=forms.PasswordInput(render_value=False),
            help_text="Пароль для входа врача (username+password). При редактировании можно оставить пустым.",
        )

        class Meta:
            model = ProfessionalAccount
            fields = ("professional", "phone", "username", "password")

        def clean_username(self):
            username = (self.cleaned_data.get("username") or "").strip()
            if not username:
                raise forms.ValidationError("Обязательное поле")

            # ensure it doesn't conflict with other users
            existing = User.objects.filter(username=username)
            if self.instance and getattr(self.instance, "user_id", None):
                existing = existing.exclude(id=self.instance.user_id)
            if existing.exists():
                raise forms.ValidationError("Такой username уже используется")
            return username

        def clean(self):
            cleaned = super().clean()
            if not self.instance.pk and not cleaned.get("password"):
                raise forms.ValidationError({"password": "Пароль обязателен при создании"})
            return cleaned

        def save(self, commit=True):
            instance: ProfessionalAccount = super().save(commit=False)
            password = self.cleaned_data.get("password")

            if instance.user_id:
                user = instance.user
                user.username = instance.username
                if password:
                    user.set_password(password)
                if commit:
                    user.save()
            else:
                user = User(username=instance.username)
                user.set_password(password)
                if commit:
                    user.save()
                instance.user = user

            if commit:
                instance.save()
            return instance

    form = ProfessionalAccountForm
    list_display = ("id", "username", "phone", "professional", "created_at")
    search_fields = ("username", "phone", "professional__full_name")
    ordering = ("id",)
