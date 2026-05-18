from rest_framework import serializers

from apps.clinic.models import Booking, Doctor, PhoneCountry, Review, Service, Specialist


class ApiErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class SpecialistSerializer(serializers.ModelSerializer):
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


class DoctorPreviewSerializer(serializers.ModelSerializer):
    specialty = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = (
            "id",
            "full_name",
            "photo_url",
            "specialty",
            "rating",
            "experience_years",
        )

    def get_specialty(self, obj: Doctor) -> str:
        if obj.primary_specialist_id:
            return obj.primary_specialist.title
        return ""

    def get_rating(self, obj: Doctor) -> float:
        # DecimalField в JSON может сериализоваться как строка — явно приводим к float
        return float(obj.rating or 0)


class DoctorAvailabilitySerializer(serializers.Serializer):
    label = serializers.CharField()
    slots = serializers.ListField(child=serializers.CharField())
    more_count = serializers.IntegerField()


class DoctorPreviewWithAvailabilitySerializer(DoctorPreviewSerializer):
    availability = DoctorAvailabilitySerializer()

    class Meta(DoctorPreviewSerializer.Meta):
        fields = DoctorPreviewSerializer.Meta.fields + ("availability",)


class PaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    limit = serializers.IntegerField()
    total = serializers.IntegerField()


class SpecialistsListResponseSerializer(serializers.Serializer):
    data = SpecialistSerializer(many=True)


class DoctorsListResponseSerializer(serializers.Serializer):
    data = DoctorPreviewWithAvailabilitySerializer(many=True)
    pagination = PaginationSerializer()


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("id", "name", "price", "duration_min", "description")


class ReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ("id", "patient_name", "patient_avatar", "rating", "text", "date")

    def get_patient_name(self, obj: Review) -> str:
        if obj.patient and obj.patient.full_name:
            return obj.patient.full_name
        if obj.patient and obj.patient.user:
            return obj.patient.user.username
        return ""

    def get_date(self, obj: Review) -> str:
        return obj.created_at.date().isoformat()


class DoctorDetailSerializer(serializers.ModelSerializer):
    specialties = serializers.SerializerMethodField()
    services = ServiceSerializer(many=True)
    reviews = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = (
            "id",
            "full_name",
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
            "gender",
            "slot_duration_min",
            "services",
            "reviews",
        )

    def get_rating(self, obj: Doctor) -> float:
        return float(obj.rating or 0)

    def get_languages(self, obj: Doctor):
        # в БД храним как "ru,kg", на фронт отдаём массив
        if not obj.languages:
            return []
        return [x.strip() for x in obj.languages.split(",") if x.strip()]

    def get_specialties(self, obj: Doctor):
        return list(
            obj.doctor_specialties.select_related("specialist")
            .order_by("-is_primary", "specialist__sort_order")
            .values_list("specialist__title", flat=True)
        )

    def get_reviews(self, obj: Doctor):
        qs = obj.reviews.filter(is_approved=True).order_by("-created_at")
        return {
            # фронт сейчас ожидает большое число (как в моках),
            # но реальные items берём из таблицы reviews.
            "total_count": max(obj.rating_count, qs.count()),
            "items": ReviewSerializer(qs[:10], many=True).data,
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
        request = self.context.get("request")
        if obj.flag:
            url = obj.flag.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return ""


class SendOtpResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    expires_in = serializers.IntegerField()
    # только DEV
    dev_code = serializers.CharField(required=False)


class VerifyOtpResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField(required=False)
    token_type = serializers.CharField()
    is_new_patient = serializers.BooleanField()


class VerifyPhoneCodeResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()


class CreateBookingSerializer(serializers.Serializer):
    doctor_id = serializers.IntegerField()
    date = serializers.DateField()
    time = serializers.TimeField()
    service_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )


class BookingDoctorSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    photo_url = serializers.CharField()
    specialty = serializers.CharField()
    clinic_address = serializers.CharField()


class BookingServiceShortSerializer(serializers.Serializer):
    name = serializers.CharField()
    price = serializers.IntegerField()


class BookingCreateDataSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    confirmation_code = serializers.CharField()
    doctor = BookingDoctorSerializer()
    date = serializers.DateField()
    time = serializers.CharField()
    services = BookingServiceShortSerializer(many=True)
    total_price = serializers.IntegerField()
    status = serializers.CharField()


class BookingCreateResponseSerializer(serializers.Serializer):
    data = BookingCreateDataSerializer()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class CalendarDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    label = serializers.CharField()
    is_available = serializers.BooleanField()
    slots_count = serializers.IntegerField()
    times = serializers.ListField(child=serializers.CharField())


class DoctorCalendarResponseSerializer(serializers.Serializer):
    data = CalendarDaySerializer(many=True)


class ReviewsPaginatedResponseSerializer(serializers.Serializer):
    data = ReviewSerializer(many=True)
    pagination = PaginationSerializer()


class CreateReviewSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(allow_blank=True, required=False)


class BookingItemSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name")
    date = serializers.DateField(source="booking_date")
    time = serializers.TimeField(source="booking_time", format="%H:%M")

    class Meta:
        model = Booking
        fields = (
            "id",
            "confirmation_code",
            "doctor_name",
            "date",
            "time",
            "status",
            "total_price",
        )


class MyBookingsResponseSerializer(serializers.Serializer):
    data = BookingItemSerializer(many=True)