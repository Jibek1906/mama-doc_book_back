from rest_framework import serializers

from django.conf import settings

from .utils import is_supported_phone, normalize_phone, public_absolute_url

from apps.organizations.models import Booking, Professional, PhoneCountry, Review, Service, Specialist, ProjectFeatureSettings
from apps.organizations.models import ProfessionalSchedule, ScheduleException
from apps.organizations.models import PaymentIntent, Branch


class GenderInputField(serializers.Field):
    """Accept gender as either boolean or string and normalize to 'male'/'female'.

    - boolean: true -> 'male', false -> 'female'
    - string: 'male'/'female' (case-insensitive)
    """

    default_error_messages = {
        "invalid": "gender должно быть boolean (true/false) или строкой 'male'/'female'",
    }

    def to_internal_value(self, data):
        if data is None or data == "":
            return None

        if isinstance(data, bool):
            return "male" if data else "female"

        if isinstance(data, str):
            v = data.strip().lower()
            if v in {"male", "m", "man", "м", "муж", "мужской"}:
                return "male"
            if v in {"female", "f", "woman", "ж", "жен", "женский"}:
                return "female"

        self.fail("invalid")

    def to_representation(self, value):
        # For output (if ever used) keep canonical values.
        if not value:
            return ""
        return str(value)


class ApiErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class SpecialistSerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Specialist
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "icon_url",
            "is_active",
            "sort_order",
        )

    def get_icon_url(self, obj: Specialist) -> str:
        if obj.icon_url:
            raw = str(obj.icon_url)
            # Если в БД лежит путь до static (seed), не добавляем /media/
            if raw.startswith("/static/") or raw.startswith("static/"):
                path = raw if raw.startswith("/") else f"/{raw}"
                return public_absolute_url(path)

            url = obj.icon_url.url
            return public_absolute_url(url)
        return ""


class ProfessionalPreviewSerializer(serializers.ModelSerializer):
    specialty = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Professional
        fields = (
            "id",
            "full_name",
            "slug",
            "photo_url",
            "specialty",
            "rating",
            "experience_years",
            "branches",
        )

    branches = serializers.SerializerMethodField()

    def get_branches(self, obj: Professional):
        # We can safely use obj.branches.all() since it should be prefetch_related where possible,
        # but to keep previews light we just map them directly. 
        return [{"id": b.id, "title": b.title, "address": b.address, "organization_id": b.organization_id} for b in obj.branches.all()]

    def get_photo_url(self, obj: Professional) -> str:
        if obj.photo_url:
            raw = str(obj.photo_url)
            if raw.startswith("/static/") or raw.startswith("static/"):
                path = raw if raw.startswith("/") else f"/{raw}"
                return public_absolute_url(path)

            url = obj.photo_url.url
            return public_absolute_url(url)
        return ""

    def get_specialty(self, obj: Professional) -> str:
        if obj.primary_specialist_id:
            return obj.primary_specialist.title
        return ""

    def get_rating(self, obj: Professional) -> float:
        # DecimalField в JSON может сериализоваться как строка — явно приводим к float
        return float(obj.rating or 0)


class ProfessionalAvailabilitySerializer(serializers.Serializer):
    label = serializers.CharField()
    slots = serializers.ListField(child=serializers.CharField())
    more_count = serializers.IntegerField()


class ProfessionalPreviewWithAvailabilitySerializer(ProfessionalPreviewSerializer):
    availability = ProfessionalAvailabilitySerializer()

    class Meta(ProfessionalPreviewSerializer.Meta):
        fields = ProfessionalPreviewSerializer.Meta.fields + ("availability",)


class PaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    limit = serializers.IntegerField()
    total = serializers.IntegerField()


class SpecialistsListResponseSerializer(serializers.Serializer):
    data = SpecialistSerializer(many=True)


class ProfessionalsListResponseSerializerLegacy(serializers.Serializer):
    data = ProfessionalPreviewWithAvailabilitySerializer(many=True)
    pagination = PaginationSerializer()


class ProfessionalsListResponseSerializer(serializers.Serializer):
    data = ProfessionalPreviewWithAvailabilitySerializer(many=True)
    pagination = PaginationSerializer()


class ServiceSerializer(serializers.ModelSerializer):
    """Public Service DTO.

    Intentionally does NOT expose professional_id/professional_ids to keep frontend contract simple.
    If frontend needs services for a specific professional, it should use:
      GET /services?professional_id=<id>
    """

    class Meta:
        model = Service
        fields = (
            "id",
            "name",
            "price",
            "duration_min",
            "description",
        )


class ServicesListResponseSerializer(serializers.Serializer):
    data = ServiceSerializer(many=True)
    pagination = PaginationSerializer()


class ProfessionalAvailableServicesResponseSerializer(serializers.Serializer):
    """Services that can start at the given date+time for a professional."""

    data = ServiceSerializer(many=True)


class ProfessionalAvailableTimesResponseSerializer(serializers.Serializer):
    """Times that can start for the given services on a selected date."""

    date = serializers.DateField()
    duration_min = serializers.IntegerField()
    times = serializers.ListField(child=serializers.CharField())


class ReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField(method_name="get_patient_name")
    date = serializers.SerializerMethodField()
    client_avatar = serializers.SerializerMethodField(method_name="get_client_avatar")

    class Meta:
        model = Review
        fields = (
            "id",
            "patient_name",
            "client_avatar",
            "rating",
            "text",
            "date",
        )

    def get_patient_name(self, obj: Review) -> str:
        if obj.client and obj.client.full_name:
            return obj.client.full_name
        if obj.client and obj.client.user:
            return obj.client.user.username
        return ""

    def get_date(self, obj: Review) -> str:
        return obj.created_at.date().isoformat()

    def get_client_avatar(self, obj: Review) -> str:
        """Return absolute patient avatar URL.

        Priority:
        1) Client.photo (ImageField)
        2) Review.client_avatar (legacy string)
        """

        if getattr(obj, "client", None) and getattr(obj.client, "photo", None):
            url = obj.client.photo.url
            return public_absolute_url(url)

        raw = (getattr(obj, "client_avatar", "") or "").strip()
        if not raw:
            return ""
        if raw.startswith("http://") or raw.startswith("https://"):
            return public_absolute_url(raw)
        # allow stored relative path
        if raw.startswith("/"):
            return public_absolute_url(raw)
        return public_absolute_url(f"/{raw}")


class ProfessionalDetailSerializer(serializers.ModelSerializer):
    specialties = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    services = ServiceSerializer(many=True)
    reviews = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    paylink_enabled = serializers.SerializerMethodField()
    clinic_name = serializers.CharField(source="organization_name")
    clinic_address = serializers.CharField(source="organization_address")

    class Meta:
        model = Professional
        fields = (
            "id",
            "full_name",
            "slug",
            "photo_url",
            "specialties",
            "rating",
            "rating_count",
            "experience_years",
            "bio",
            "education",
            "clinic_name",
            "clinic_address",
            "consultation_type",
            "languages",
            "is_accepting_new",
            "is_active",
            "paylink_enabled",
            "gender",
            "slot_duration_min",
            "services",
            "reviews",
            "branches",
        )
    
    branches = serializers.SerializerMethodField()

    def get_branches(self, obj: Professional):
        # Return basic branch info so frontend knows which organizations/branches this specialist belongs to
        return [{"id": b.id, "title": b.title, "address": b.address, "organization_id": b.organization_id} for b in obj.branches.all()]

    def get_photo_url(self, obj: Professional) -> str:
        if obj.photo_url:
            raw = str(obj.photo_url)
            if raw.startswith("/static/") or raw.startswith("static/"):
                path = raw if raw.startswith("/") else f"/{raw}"
                return public_absolute_url(path)

            url = obj.photo_url.url
            return public_absolute_url(url)
        return ""

    def get_rating(self, obj: Professional) -> float:
        return float(obj.rating or 0)

    def get_languages(self, obj: Professional) -> list[str]:
        # в БД храним как "ru,kg", на фронт отдаём массив
        if not obj.languages:
            return []
        return [x.strip() for x in obj.languages.split(",") if x.strip()]

    def get_paylink_enabled(self, obj: Professional) -> bool:
        feature_settings = ProjectFeatureSettings.objects.order_by("id").first()
        global_enabled = bool(getattr(settings, "FEATURE_PAYLINK_ENABLED", True))
        if feature_settings is not None:
            global_enabled = global_enabled and bool(feature_settings.paylink_enabled)

        org_enabled = True
        if obj.branches.exists():
            org_enabled = any(b.organization.paylink_enabled for b in obj.branches.select_related("organization").all() if b.organization)

        return bool(global_enabled and org_enabled and bool(getattr(obj, "paylink_enabled", True)))

    def get_specialties(self, obj: Professional) -> list[str]:
        return list(
            obj.professional_specialties.select_related("specialist")
            .order_by("-is_primary", "specialist__sort_order")
            .values_list("specialist__title", flat=True)
        )

    def get_reviews(self, obj: Professional) -> dict:
        qs = obj.reviews.filter(is_approved=True).order_by("-created_at")
        return {
            # фронт сейчас ожидает большое число (как в моках),
            # но реальные items берём из таблицы reviews.
            "total_count": max(obj.rating_count, qs.count()),
            "items": ReviewSerializer(qs[:10], many=True, context=self.context).data,
        }


class SendOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


# совместимость с шаблоном PHONE_AUTH_FLOW_TEMPLATE
class PhoneSendCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)


class PhoneVerifyCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class VerifyOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class PhoneCountrySerializer(serializers.ModelSerializer):
    flag = serializers.SerializerMethodField()

    class Meta:
        model = PhoneCountry
        fields = ("code", "name", "dial_code", "flag")

    def get_flag(self, obj: PhoneCountry) -> str:
        if obj.flag:
            url = obj.flag.url
            return public_absolute_url(url)
        return ""


class SendOtpResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    expires_in = serializers.IntegerField()
    # только DEV
    dev_code = serializers.CharField(required=False)


class VerifyOtpResponseSerializer(serializers.Serializer):
    """Response for patient OTP verification.

    If profile already completed -> returns access_token.
    Otherwise -> returns phone and code for step-3 completion.
    """

    needs_profile = serializers.BooleanField()
    is_new_patient = serializers.BooleanField()

    # when needs_profile=false
    access_token = serializers.CharField(required=False)
    refresh_token = serializers.CharField(required=False)
    token_type = serializers.CharField(required=False)

    # when needs_profile=true
    phone = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


class VerifyPhoneCodeResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()


class CompleteClientProfileSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
        help_text=(
            "Поддерживаемые форматы: +996XXXXXXXXX или +7XXXXXXXXXX. "
            "Также можно отправлять без '+': 996XXXXXXXXX, 7XXXXXXXXXX, 8777..., "
            "а для KG можно 0706... или 706... — будет нормализовано."
        ),
    )
    # All fields except phone must be optional and allow sending empty values.
    # We accept both "" and null where applicable.
    full_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    inn = serializers.IntegerField(required=False, allow_null=True, default=None)
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    # GenderInputField already returns None for ""/null.
    gender = GenderInputField(required=False, allow_null=True)
    nickname = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    telegram = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    instagram = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

    def validate_phone(self, value: str) -> str:
        phone = normalize_phone(value)
        if not is_supported_phone(phone):
            raise serializers.ValidationError("Неверный формат телефона")
        return phone

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            for key in ["inn", "birth_date"]:
                if key in data and data[key] == "":
                    data[key] = None
        return super().to_internal_value(data)


class CompleteClientProfileResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()


# --- Professional cabinet (/v1/pro/*) ---


class ProLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ProSendOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class ProVerifyOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class ProAuthResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()


class ProMeSerializer(serializers.Serializer):
    professional_id = serializers.IntegerField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    username = serializers.CharField()


class ProScheduleItemSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    end_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    break_start = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    break_end = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)

    class Meta:
        model = ProfessionalSchedule
        fields = ("id", "day_of_week", "is_working", "start_time", "end_time", "break_start", "break_end")


class ProScheduleUpdateSerializer(serializers.Serializer):
    items = ProScheduleItemSerializer(many=True)

    def validate(self, attrs):
        items = attrs.get("items") or []
        days = [i.get("day_of_week") for i in items]
        if len(days) != len(set(days)):
            raise serializers.ValidationError({"items": ["day_of_week должен быть уникальным"]})
        for d in days:
            if d is None or int(d) < 0 or int(d) > 6:
                raise serializers.ValidationError({"items": ["day_of_week должен быть 0..6"]})
        return attrs


class ProScheduleExceptionSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(format="%H:%M", required=False, allow_null=True)
    end_time = serializers.TimeField(format="%H:%M", required=False, allow_null=True)
    break_start = serializers.TimeField(format="%H:%M", required=False, allow_null=True)
    break_end = serializers.TimeField(format="%H:%M", required=False, allow_null=True)

    class Meta:
        model = ScheduleException
        fields = ("id", "date", "is_day_off", "reason", "start_time", "end_time", "break_start", "break_end")


class ProScheduleExceptionCreateSerializer(serializers.Serializer):
    date = serializers.DateField()
    is_day_off = serializers.BooleanField(default=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    
    start_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    end_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    break_start = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    break_end = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)


class PartnerBookingSerializer(serializers.ModelSerializer):
    date = serializers.DateField(source="booking_date", format="%d.%m.%Y")
    time = serializers.TimeField(source="booking_time", format="%H:%M")
    patient_phone = serializers.CharField(source="client.phone")
    patient_name = serializers.CharField(source="client.full_name")
    services = serializers.SerializerMethodField()
    professional_id = serializers.IntegerField(source="professional.id")
    professional_name = serializers.CharField(source="professional.full_name")
    updated_at = serializers.DateTimeField()

    class Meta:
        model = Booking
        fields = (
            "id", "confirmation_code", "date", "time", "status", "total_price", 
            "patient_phone", "patient_name", "services", "professional_id", 
            "professional_name", "updated_at"
        )

    def get_services(self, obj):
        return [{"id": bs.service_id, "name": bs.service.name} for bs in obj.booking_services.all()]

class ProBookingSerializer(serializers.ModelSerializer):
    date = serializers.DateField(source="booking_date")
    time = serializers.TimeField(source="booking_time", format="%H:%M")
    patient_phone = serializers.CharField(source="client.phone")
    patient_name = serializers.CharField(source="client.full_name")
    patient_photo_url = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ("id", "confirmation_code", "date", "time", "status", "total_price", "total_duration_min", "patient_phone", "patient_name", "patient_photo_url", "services")

    def get_patient_photo_url(self, obj):
        if obj.client and obj.client.photo:
            return public_absolute_url(obj.client.photo.url)
        return ""

    def get_services(self, obj):
        return [{"id": bs.service_id, "name": bs.service.name} for bs in obj.booking_services.all()]


class CreateBookingSerializer(serializers.Serializer):
    professional_id = serializers.IntegerField(required=False)
    date = serializers.DateField()
    # accept only HH:MM to keep frontend contract simple
    time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    service_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )

    def validate(self, attrs):
        professional_id = attrs.get("professional_id")
        if professional_id is None:
            raise serializers.ValidationError({"professional_id": ["Обязательный параметр"]})
        return attrs


class BookingProfessionalSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    photo_url = serializers.CharField()
    specialty = serializers.CharField()
    clinic_address = serializers.CharField(source="organization_address")


class BookingServiceShortSerializer(serializers.Serializer):
    name = serializers.CharField()
    price = serializers.IntegerField()


class BookingCreateDataSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    confirmation_code = serializers.CharField()
    organization_id = serializers.IntegerField(allow_null=True)
    branch_id = serializers.IntegerField(allow_null=True)
    professional = BookingProfessionalSerializer()
    date = serializers.DateField()
    time = serializers.CharField()
    services = BookingServiceShortSerializer(many=True)
    total_price = serializers.IntegerField()
    status = serializers.CharField()


class BookingCreateResponseSerializer(serializers.Serializer):
    data = BookingCreateDataSerializer()


class CreatePaylinkSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField()

    def validate_branch_id(self, value: int) -> int:
        if not Branch.objects.filter(id=value, is_active=True, organization__is_active=True).exists():
            raise serializers.ValidationError("Филиал не найден")
        return value


class CreatePaylinkResponseSerializer(serializers.Serializer):
    payment_intent_id = serializers.IntegerField()
    transaction_id = serializers.UUIDField()
    amount = serializers.IntegerField()
    paylink_url = serializers.URLField()


class PaymentWebhookSerializer(serializers.Serializer):
    # Based on example payload from bank/service.
    account_no = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.FloatField(required=False)
    currency_id = serializers.IntegerField(required=False)
    currency_code = serializers.CharField(required=False, allow_blank=True)
    operation_id = serializers.CharField(required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True)
    operation_state = serializers.CharField(required=False, allow_blank=True)
    qr_transaction_id = serializers.CharField(required=False, allow_blank=True)
    elqr_id = serializers.CharField(required=False, allow_blank=True)


class CreateBookingV2Serializer(serializers.Serializer):
    """Booking creation that can require paid PaymentIntent for branches with paylink_enabled."""

    professional_id = serializers.IntegerField(required=False)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    payment_intent_id = serializers.IntegerField(required=False, allow_null=True)
    date = serializers.DateField()
    time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    service_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate(self, attrs):
        if attrs.get("professional_id") is None:
            raise serializers.ValidationError({"professional_id": ["Обязательный параметр"]})
        return attrs


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class CalendarDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    label = serializers.CharField()
    is_available = serializers.BooleanField()
    slots_count = serializers.IntegerField()
    times = serializers.ListField(child=serializers.CharField())


class ProfessionalCalendarResponseSerializer(serializers.Serializer):
    data = CalendarDaySerializer(many=True)


class ReviewsPaginatedResponseSerializer(serializers.Serializer):
    data = ReviewSerializer(many=True)
    pagination = PaginationSerializer()


class CreateReviewSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(allow_blank=True, required=False)



class BookingItemSerializer(serializers.ModelSerializer):
    professional_name = serializers.CharField(source="professional.full_name")
    date = serializers.DateField(source="booking_date")
    time = serializers.TimeField(source="booking_time", format="%H:%M")

    class Meta:
        model = Booking
        fields = (
            "id",
            "confirmation_code",
            "professional_name",
            "date",
            "time",
            "status",
            "total_price",
        )


class ProfessionalDetailResponseSerializer(serializers.Serializer):
    data = ProfessionalDetailSerializer()


class MyBookingsResponseSerializer(serializers.Serializer):
    data = BookingItemSerializer(many=True)


class OrganizationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField(required=False)
    logo_url = serializers.CharField(required=False)
    paylink_enabled = serializers.BooleanField(required=False)
    specialists_count = serializers.IntegerField()
    professionals_count = serializers.IntegerField()
    services_count = serializers.IntegerField(required=False)
    branches = serializers.ListField(child=serializers.DictField(), required=False)


class BranchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.CharField(required=False)
    address = serializers.CharField()
    professionals_count = serializers.IntegerField()
    paylink_enabled = serializers.BooleanField(required=False)
    paylink_amount = serializers.IntegerField(required=False)


class BranchScheduleItemSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField()
    is_working = serializers.BooleanField()
    start_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    end_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    break_start = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)
    break_end = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"], required=False, allow_null=True)


class BranchDetailSerializer(BranchSerializer):
    schedule = BranchScheduleItemSerializer(many=True)


class BranchDetailResponseSerializer(serializers.Serializer):
    data = BranchDetailSerializer()


class FeatureFlagsSerializer(serializers.Serializer):
    branches_enabled = serializers.BooleanField()
    paylink_enabled = serializers.BooleanField()

    # paylink_scopes
    paylink_by_organization = serializers.BooleanField(required=False)
    paylink_by_professional = serializers.BooleanField(required=False)


class OrganizationsListResponseSerializer(serializers.Serializer):
    data = OrganizationSerializer(many=True)


class OrganizationDetailResponseSerializer(serializers.Serializer):
    data = OrganizationSerializer()


class BranchesListResponseSerializer(serializers.Serializer):
    data = BranchSerializer(many=True)
