import random
import requests
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import OpenApiResponse, extend_schema

from apps.clinic.models import (
    Booking,
    Doctor,
    OTPCode,
    Patient,
    PhoneCountry,
    Review,
    SMSCode,
    Service,
    Specialist,
)

from .serializers import (
    BookingItemSerializer,
    CreateBookingSerializer,
    CreateReviewSerializer,
    DoctorDetailSerializer,
    DoctorPreviewSerializer,
    DoctorCalendarResponseSerializer,
    DoctorsListResponseSerializer,
    MessageResponseSerializer,
    MyBookingsResponseSerializer,
    PhoneCountrySerializer,
    ReviewsPaginatedResponseSerializer,
    ReviewSerializer,
    SendOtpSerializer,
    SendOtpResponseSerializer,
    SpecialistSerializer,
    SpecialistsListResponseSerializer,
    PhoneSendCodeSerializer,
    PhoneVerifyCodeSerializer,
    VerifyOtpSerializer,
    VerifyOtpResponseSerializer,
    VerifyPhoneCodeResponseSerializer,
    BookingCreateResponseSerializer,
)
from .utils import api_error, bishek_now, label_for_day, make_confirmation_code


def _create_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }


def health(request):
    return JsonResponse({"status": "ok"})


class DefaultPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    page_query_param = "page"
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response(
            {
                "data": data,
                "pagination": {
                    "page": int(self.request.query_params.get("page", 1)),
                    "limit": self.get_page_size(self.request),
                    "total": self.page.paginator.count,
                },
            }
        )


class SpecialistListAPIView(APIView):
    @extend_schema(
        summary="Список специализаций",
        auth=[],
        responses={200: SpecialistsListResponseSerializer},
    )
    def get(self, request):
        qs = Specialist.objects.filter(is_active=True).order_by("sort_order", "id")
        return Response({"data": SpecialistSerializer(qs, many=True, context={"request": request}).data})


class DoctorListAPIView(APIView):
    pagination_class = DefaultPagination

    @extend_schema(
        summary="Список врачей (карточки)",
        auth=[],
        responses={200: DoctorsListResponseSerializer},
    )
    def get(self, request):
        qs = Doctor.objects.filter(is_active=True).select_related("primary_specialist")

        specialist_id = request.query_params.get("specialist_id")
        search = request.query_params.get("search")
        if specialist_id:
            qs = qs.filter(primary_specialist_id=int(specialist_id))
        if search:
            qs = qs.filter(full_name__icontains=search)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs.order_by("id"), request)

        data = []
        for doctor in page:
            day = doctor.get_first_available_day(days=30)
            availability = {"label": "", "slots": [], "more_count": 0}
            if day:
                availability = {
                    "label": label_for_day(day["date"]),
                    "slots": day["times"][:3],
                    "more_count": max(0, len(day["times"]) - 3),
                }
            data.append(
                DoctorPreviewSerializer(doctor, context={"request": request}).data
                | {"availability": availability}
            )

        return paginator.get_paginated_response(data)


class DoctorDetailAPIView(APIView):
    @extend_schema(
        summary="Детали врача",
        auth=[],
        responses={
            200: DoctorDetailSerializer,
            404: OpenApiResponse(description="not_found"),
        },
    )
    def get(self, request, doctor_id: int):
        try:
            doctor = (
                Doctor.objects.filter(is_active=True)
                .prefetch_related("services", "doctor_specialties__specialist")
                .get(id=doctor_id)
            )
        except Doctor.DoesNotExist:
            return Response(api_error(error="not_found", message="Врач не найден"), status=404)

        return Response({"data": DoctorDetailSerializer(doctor, context={"request": request}).data})


class DoctorCalendarAPIView(APIView):
    @extend_schema(
        summary="Календарь врача на 30 дней",
        auth=[],
        responses={200: DoctorCalendarResponseSerializer},
    )
    def get(self, request, doctor_id: int):
        try:
            doctor = Doctor.objects.get(id=doctor_id, is_active=True)
        except Doctor.DoesNotExist:
            return Response(api_error(error="not_found", message="Врач не найден"), status=404)

        return Response({"data": doctor.get_calendar(days=30)})


class DoctorReviewsAPIView(APIView):
    pagination_class = DefaultPagination

    def get_permissions(self):
        # self.request может быть None при генерации schema
        if getattr(getattr(self, "request", None), "method", "GET") == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_authenticators(self):
        if getattr(getattr(self, "request", None), "method", "GET") == "POST":
            return [JWTAuthentication()]
        return []

    @extend_schema(
        summary="Отзывы врача (публичные)",
        auth=[],
        responses={200: ReviewsPaginatedResponseSerializer},
    )
    def get(self, request, doctor_id: int):
        qs = Review.objects.filter(doctor_id=doctor_id, is_approved=True).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ReviewSerializer(page, many=True).data)

    @extend_schema(
        summary="Оставить отзыв (требует авторизации)",
        request=CreateReviewSerializer,
        responses={
            201: OpenApiResponse(description="Отзыв отправлен на модерацию"),
            400: OpenApiResponse(description="invalid"),
        },
    )
    def post(self, request, doctor_id: int):
        s = CreateReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        booking_id = s.validated_data["booking_id"]
        rating = s.validated_data["rating"]
        text = s.validated_data.get("text", "")

        try:
            patient = Patient.objects.get(user=request.user)
        except Patient.DoesNotExist:
            return Response(api_error(error="invalid", message="Пациент не найден"), status=400)

        try:
            booking = Booking.objects.get(id=booking_id, patient=patient, doctor_id=doctor_id)
        except Booking.DoesNotExist:
            return Response(api_error(error="invalid", message="Запись не найдена"), status=400)

        Review.objects.create(
            doctor_id=doctor_id,
            patient=patient,
            booking=booking,
            rating=int(rating),
            text=text,
            is_approved=False,
        )
        return Response({"message": "Отзыв отправлен на модерацию"}, status=201)


class SendOtpAPIView(APIView):
    @extend_schema(
        summary="Отправить OTP",
        auth=[],
        request=SendOtpSerializer,
        responses={
            200: SendOtpResponseSerializer,
            429: OpenApiResponse(description="too_many_requests"),
        },
    )
    def post(self, request):
        s = SendOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = s.validated_data["phone"]

        existing = (
            SMSCode.objects.filter(
                phone_number=phone,
                purpose=SMSCode.PURPOSE_LOGIN,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )
        if existing and existing.expires_at > timezone.now():
            retry_after = int((existing.expires_at - timezone.now()).total_seconds())
            return Response(
                api_error(
                    error="too_many_requests",
                    message="Подождите перед повторной отправкой",
                    details={"retry_after": retry_after},
                ),
                status=429,
            )

        code = f"{random.randint(0, 999999):06d}"
        expires_at = timezone.now() + timedelta(seconds=60)
        SMSCode.objects.create(
            phone_number=phone,
            code=code,
            purpose=SMSCode.PURPOSE_LOGIN,
            payload={"flow": "phone"},
            expires_at=expires_at,
        )

        from django.conf import settings

        payload = {"message": "Код отправлен", "expires_in": 60}
        
        # Если DEV_OTP_BYPASS включен и номер совпадает с тестовым
        if getattr(settings, "DEV_OTP_BYPASS", False) and phone == getattr(settings, "DEV_OTP_PHONE", ""):
            payload["dev_code"] = code
        else:
            # Реальная отправка SMS
            login = getattr(settings, "SMS_LOGIN", "")
            password = getattr(settings, "SMS_PASSWORD", "")
            sender = getattr(settings, "SMS_SENDER", "")
            
            if login and password and sender:
                xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
    <login>{login}</login>
    <pwd>{password}</pwd>
    <sender>{sender}</sender>
    <text>Код подтверждения: {code}</text>
    <phones>
        <phone>{phone}</phone>
    </phones>
</message>"""
                try:
                    url = getattr(settings, "SMS_API_URL", "https://smspro.nikita.kg/api/message")
                    requests.post(url, data=xml_data.encode('utf-8'), headers={"Content-Type": "application/xml"}, timeout=10)
                except Exception as e:
                    print(f"SMS sending error: {e}")

        return Response(payload)


class VerifyOtpAPIView(APIView):
    @extend_schema(
        summary="Проверить OTP и получить access_token",
        auth=[],
        request=VerifyOtpSerializer,
        responses={
            200: VerifyOtpResponseSerializer,
            400: OpenApiResponse(description="invalid_code"),
        },
    )
    def post(self, request):
        s = VerifyOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = s.validated_data["phone"]
        code = s.validated_data["code"]

        from django.conf import settings

        if settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE and code == settings.DEV_OTP_CODE:
            user, created = User.objects.get_or_create(username=phone)
            Patient.objects.get_or_create(user=user, defaults={"phone": phone})
            tokens = _create_tokens_for_user(user)
            return Response(
                {
                    **tokens,
                    "token_type": "bearer",
                    "is_new_patient": created,
                }
            )

        sms = (
            SMSCode.objects.filter(
                phone_number=phone,
                purpose=SMSCode.PURPOSE_LOGIN,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )
        if not sms or sms.expires_at <= timezone.now():
            return Response(api_error(error="invalid_code", message="Код истёк или не найден"), status=400)

        if sms.code != code:
            sms.attempts += 1
            sms.save(update_fields=["attempts"])
            attempts_left = max(0, 5 - sms.attempts)
            return Response(
                api_error(
                    error="invalid_code",
                    message="Неверный код",
                    details={"attempts_left": attempts_left},
                ),
                status=400,
            )

        sms.is_used = True
        sms.save(update_fields=["is_used"])

        user, created = User.objects.get_or_create(username=phone)
        Patient.objects.get_or_create(user=user, defaults={"phone": phone})

        tokens = _create_tokens_for_user(user)
        return Response(
            {
                **tokens,
                "token_type": "bearer",
                "is_new_patient": created,
            }
        )


class BookingCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Создать запись (требует авторизации)",
        request=CreateBookingSerializer,
        responses={
            201: BookingCreateResponseSerializer,
            409: OpenApiResponse(description="slot_unavailable"),
        },
    )
    @transaction.atomic
    def post(self, request):
        s = CreateBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            patient = Patient.objects.get(user=request.user)
        except Patient.DoesNotExist:
            return Response(api_error(error="invalid", message="Пациент не найден"), status=400)

        try:
            doctor = Doctor.objects.get(id=data["doctor_id"], is_active=True)
        except Doctor.DoesNotExist:
            return Response(api_error(error="not_found", message="Врач не найден"), status=404)

        services = list(Service.objects.filter(doctor=doctor, id__in=data["service_ids"], is_active=True))
        if len(services) != len(set(data["service_ids"])):
            return Response(api_error(error="invalid", message="Некоторые услуги не найдены"), status=400)

        exists = Booking.objects.filter(
            doctor=doctor,
            booking_date=data["date"],
            booking_time=data["time"],
        ).exclude(status="cancelled").exists()
        if exists:
            return Response(
                api_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                ),
                status=409,
            )

        total_price = sum(svc.price for svc in services)
        total_duration_min = sum(svc.duration_min for svc in services)

        confirmation_code = make_confirmation_code()
        for _ in range(10):
            if not Booking.objects.filter(confirmation_code=confirmation_code).exists():
                break
            confirmation_code = make_confirmation_code()

        booking = Booking.objects.create(
            patient=patient,
            doctor=doctor,
            booking_date=data["date"],
            booking_time=data["time"],
            status="confirmed",
            confirmation_code=confirmation_code,
            total_price=total_price,
            total_duration_min=total_duration_min,
        )
        booking.set_services(services)

        return Response(
            {
                "data": {
                    "id": booking.id,
                    "confirmation_code": booking.confirmation_code,
                    "doctor": {
                        "full_name": doctor.full_name,
                        "photo_url": DoctorPreviewSerializer(
                            doctor, context={"request": request}
                        ).data.get("photo_url", ""),
                        "specialty": doctor.primary_specialist.title if doctor.primary_specialist_id else "",
                        "clinic_address": doctor.clinic_address,
                    },
                    "date": booking.booking_date.isoformat(),
                    "time": booking.booking_time.strftime("%H:%M"),
                    "services": [{"name": svc.name, "price": svc.price} for svc in services],
                    "total_price": total_price,
                    "status": booking.status,
                }
            },
            status=201,
        )





class PhoneCountriesAPIView(APIView):
    @extend_schema(
        summary="Список стран телефонов",
        auth=[],
        responses={200: PhoneCountrySerializer(many=True)},
    )
    def get(self, request):
        qs = PhoneCountry.objects.all()
        return Response(PhoneCountrySerializer(qs, many=True, context={"request": request}).data)


class MyBookingsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Мои записи (требует авторизации)",
        responses={200: MyBookingsResponseSerializer},
    )
    def get(self, request):
        try:
            patient = Patient.objects.get(user=request.user)
        except Patient.DoesNotExist:
            return Response({"data": []})

        qs = Booking.objects.filter(patient=patient).select_related("doctor").order_by("-created_at")
        return Response({"data": BookingItemSerializer(qs, many=True).data})


class CancelBookingAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Отменить запись (требует авторизации)",
        responses={
            200: MessageResponseSerializer,
            400: OpenApiResponse(description="cannot_cancel"),
            404: OpenApiResponse(description="not_found"),
        },
    )
    def delete(self, request, booking_id: int):
        try:
            patient = Patient.objects.get(user=request.user)
        except Patient.DoesNotExist:
            return Response(api_error(error="invalid", message="Пациент не найден"), status=400)

        try:
            booking = Booking.objects.get(id=booking_id, patient=patient)
        except Booking.DoesNotExist:
            return Response(api_error(error="not_found", message="Запись не найдена"), status=404)

        appt_dt = timezone.make_aware(
            timezone.datetime.combine(booking.booking_date, booking.booking_time)
        )
        if appt_dt - bishek_now() < timedelta(hours=2):
            return Response(
                api_error(
                    error="cannot_cancel",
                    message="Отменить запись можно не позднее чем за 2 часа до приёма",
                ),
                status=400,
            )

        booking.status = "cancelled"
        booking.cancelled_by = "patient"
        booking.save(update_fields=["status", "cancelled_by", "updated_at"])
        return Response({"message": "Запись отменена"})
