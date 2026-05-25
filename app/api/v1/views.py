import random
import requests
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, When
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)

from apps.organizations.models import (
    Booking,
    Branch,
    Professional,
    Organization,
    OTPCode,
    Client,
    PhoneCountry,
    ProjectFeatureSettings,
    Review,
    SMSCode,
    Service,
    Specialist,
    ProfessionalAccount,
    ProfessionalSchedule,
    ScheduleException,
    PendingClientProfile,
    BranchSchedule,
)

from .serializers import (
    ApiErrorSerializer,
    BranchesListResponseSerializer,
    BookingItemSerializer,
    CreateBookingSerializer,
    CreateReviewSerializer,
    ProfessionalDetailSerializer,
    ProfessionalPreviewSerializer,
    ProfessionalCalendarResponseSerializer,
    ProfessionalsListResponseSerializerLegacy,
    FeatureFlagsSerializer,
    MessageResponseSerializer,
    MyBookingsResponseSerializer,
    OrganizationsListResponseSerializer,
    OrganizationDetailResponseSerializer,
    PhoneCountrySerializer,
    ProfessionalDetailResponseSerializer,
    ProfessionalsListResponseSerializer,
    ReviewsPaginatedResponseSerializer,
    ReviewSerializer,
    SendOtpSerializer,
    SendOtpResponseSerializer,
    ServicesListResponseSerializer,
    ServiceSerializer,
    ProfessionalAvailableServicesResponseSerializer,
    ProfessionalAvailableTimesResponseSerializer,
    SpecialistSerializer,
    SpecialistsListResponseSerializer,
    PhoneSendCodeSerializer,
    PhoneVerifyCodeSerializer,
    VerifyOtpSerializer,
    VerifyOtpResponseSerializer,
    CompleteClientProfileSerializer,
    CompleteClientProfileResponseSerializer,
    VerifyPhoneCodeResponseSerializer,
    BookingCreateResponseSerializer,

    # pro cabinet
    ProLoginSerializer,
    ProSendOtpSerializer,
    ProVerifyOtpSerializer,
    ProAuthResponseSerializer,
    ProMeSerializer,
    ProScheduleUpdateSerializer,
    ProScheduleItemSerializer,
    ProScheduleExceptionSerializer,
    ProScheduleExceptionCreateSerializer,
    ProBookingSerializer,

    BranchDetailResponseSerializer,
)
from .utils import (
    api_error,
    bishek_now,
    is_supported_phone,
    label_for_day,
    make_confirmation_code,
    normalize_phone,
    time_range,
)


@method_decorator(csrf_exempt, name="dispatch")
class CsrfExemptAPIView(APIView):
    pass


# --- OpenAPI error examples (единый формат ошибок из ТЗ) ---
EX_VALIDATION_ERROR = OpenApiExample(
    name="validation_error",
    value=api_error(
        error="validation_error",
        message="Невалидные данные",
        details={"field": ["error message"]},
    ),
    response_only=True,
)

EX_NOT_AUTHENTICATED = OpenApiExample(
    name="not_authenticated",
    value=api_error(error="not_authenticated", message="Не авторизован"),
    response_only=True,
)

EX_FORBIDDEN = OpenApiExample(
    name="forbidden",
    value=api_error(error="forbidden", message="Нет доступа"),
    response_only=True,
)

EX_NOT_FOUND = OpenApiExample(
    name="not_found",
    value=api_error(error="not_found", message="Не найдено"),
    response_only=True,
)

EX_SERVER_ERROR = OpenApiExample(
    name="server_error",
    value=api_error(error="server_error", message="Ошибка сервера"),
    response_only=True,
)

EX_INVALID_PHONE = OpenApiExample(
    name="invalid_phone",
    value=api_error(error="invalid_phone", message="Неверный формат телефона"),
    response_only=True,
)

EX_TOO_MANY_REQUESTS = OpenApiExample(
    name="too_many_requests",
    value=api_error(
        error="too_many_requests",
        message="Слишком много запросов",
        details={"retry_after": 60},
    ),
    response_only=True,
)

EX_INVALID_CODE = OpenApiExample(
    name="invalid_code",
    value=api_error(
        error="invalid_code",
        message="Неверный код",
        details={"attempts_left": 3},
    ),
    response_only=True,
)

EX_PROFILE_INCOMPLETE = OpenApiExample(
    name="profile_incomplete",
    value=api_error(
        error="profile_incomplete",
        message="Профиль не заполнен",
        details={"required": ["full_name", "inn", "birth_date"]},
    ),
    response_only=True,
)

EX_SLOT_UNAVAILABLE = OpenApiExample(
    name="slot_unavailable",
    value=api_error(
        error="slot_unavailable",
        message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
    ),
    response_only=True,
)

EX_CANNOT_CANCEL = OpenApiExample(
    name="cannot_cancel",
    value=api_error(
        error="cannot_cancel",
        message="Отменить запись можно не позднее чем за 2 часа до приёма",
    ),
    response_only=True,
)

EX_CLIENT_NOT_FOUND = OpenApiExample(
    name="client_not_found",
    value=api_error(error="client_not_found", message="Клиент не найден"),
    response_only=True,
)

EX_SERVICES_NOT_FOUND = OpenApiExample(
    name="services_not_found",
    value=api_error(error="services_not_found", message="Некоторые услуги не найдены"),
    response_only=True,
)

EX_DATE_IN_PAST = OpenApiExample(
    name="date_in_past",
    value=api_error(error="date_in_past", message="Дата записи уже прошла"),
    response_only=True,
)

EX_CANNOT_REVIEW = OpenApiExample(
    name="cannot_review",
    value=api_error(
        error="cannot_review",
        message="Оставить отзыв можно только после завершённого приёма",
    ),
    response_only=True,
)


def _get_pro_account_or_unauthorized(*, request) -> tuple[ProfessionalAccount | None, Response | None]:
    """Return ProfessionalAccount based on JWT-authenticated request.user."""

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None, Response(api_error(error="not_authenticated", message="Не авторизован"), status=401)
    try:
        return request.user.professional_account, None
    except Exception:
        return None, Response(api_error(error="forbidden", message="Нет доступа"), status=403)


class ProAuthLoginAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="PRO: вход по username+password",
        auth=[],
        request=ProLoginSerializer,
        responses={200: ProAuthResponseSerializer, 400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR])},
    )
    def post(self, request):
        s = ProLoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        username = s.validated_data["username"].strip()
        password = s.validated_data["password"]

        # allow login by phone as well (admin may store phone and user.username might be custom)
        normalized_phone = None
        try:
            normalized_phone = normalize_phone(username)
        except Exception:
            normalized_phone = None

        if normalized_phone and ProfessionalAccount.objects.filter(phone=normalized_phone).exists():
            acc = ProfessionalAccount.objects.select_related("user").filter(phone=normalized_phone).first()
            if acc and acc.user:
                username = acc.user.username

        user = authenticate(username=username, password=password)
        if not user:
            return Response(api_error(error="invalid_credentials", message="Неверный логин или пароль"), status=400)

        if not ProfessionalAccount.objects.filter(user=user).exists():
            return Response(api_error(error="forbidden", message="Нет доступа"), status=403)

        tokens = _create_tokens_for_user(user)
        return Response({**tokens, "token_type": "bearer"})


class ProSendOtpAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="PRO: отправить OTP (только если телефон привязан к профессионалу)",
        auth=[],
        request=ProSendOtpSerializer,
        responses={200: SendOtpResponseSerializer, 400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_INVALID_PHONE, EX_VALIDATION_ERROR])},
    )
    def post(self, request):
        s = ProSendOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalize_phone(s.validated_data["phone"])

        if not is_supported_phone(phone):
            return Response(api_error(error="invalid_phone", message="Неверный формат телефона"), status=400)

        if not ProfessionalAccount.objects.filter(phone=phone).exists():
            return Response(api_error(error="forbidden", message="Телефон не привязан к профессионалу"), status=403)

        # reuse SMSCode with separate purpose
        code = f"{random.randint(0, 999999):06d}"
        expires_at = timezone.now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        # DEV bypass
        if settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE:
            code = settings.DEV_OTP_CODE

        SMSCode.objects.create(
            phone_number=phone,
            code=code,
            purpose=SMSCode.PURPOSE_PRO_LOGIN,
            payload={"flow": "pro"},
            expires_at=expires_at,
        )

        payload = {"message": "Код отправлен", "expires_in": settings.OTP_EXPIRE_SECONDS}
        if settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE:
            payload["dev_code"] = code
        
        if not (settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE):
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


class ProVerifyOtpAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="PRO: проверить OTP и получить access_token",
        auth=[],
        request=ProVerifyOtpSerializer,
        responses={200: ProAuthResponseSerializer, 400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_INVALID_CODE, EX_VALIDATION_ERROR])},
    )
    def post(self, request):
        s = ProVerifyOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalize_phone(s.validated_data["phone"])
        code = s.validated_data["code"]

        # ensure phone is bound to professional
        try:
            acc = ProfessionalAccount.objects.select_related("user").get(phone=phone)
        except ProfessionalAccount.DoesNotExist:
            return Response(api_error(error="forbidden", message="Телефон не привязан к профессионалу"), status=403)

        sms = (
            SMSCode.objects.filter(
                phone_number=phone,
                purpose=SMSCode.PURPOSE_PRO_LOGIN,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )
        if not sms or sms.expires_at <= timezone.now() or sms.code != code:
            return Response(api_error(error="invalid_code", message="Неверный код"), status=400)

        sms.is_used = True
        sms.save(update_fields=["is_used"])

        tokens = _create_tokens_for_user(acc.user)
        return Response({**tokens, "token_type": "bearer"})


class ProMeAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="PRO: профиль", responses={200: ProMeSerializer})
    def get(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        pro_obj = acc.professional
        return Response(
            {
                "professional_id": pro_obj.id,
                "full_name": pro_obj.full_name,
                "phone": acc.phone,
                "username": acc.username,
            }
        )


class ProCalendarAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="PRO: календарь свободных слотов", responses={200: ProfessionalCalendarResponseSerializer})
    def get(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        duration_min = request.query_params.get("duration_min")
        service_ids = request.query_params.get("service_ids")

        duration = None
        if duration_min:
            try:
                duration = int(duration_min)
            except ValueError:
                duration = None
        elif service_ids:
            try:
                ids = [int(x) for x in service_ids.split(",") if x.strip()]
                duration = sum(
                    Service.objects.filter(id__in=ids, is_active=True).values_list("duration_min", flat=True)
                )
            except Exception:
                duration = None

        return Response({"data": acc.professional.get_calendar(days=30, duration_min=duration)})


class ProScheduleAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="PRO: получить недельный график", responses={200: ProScheduleItemSerializer(many=True)})
    def get(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        qs = ProfessionalSchedule.objects.filter(professional=acc.professional).order_by("day_of_week", "id")
        return Response({"data": ProScheduleItemSerializer(qs, many=True).data})

    @extend_schema(summary="PRO: заменить недельный график", request=ProScheduleUpdateSerializer, responses={200: MessageResponseSerializer})
    @transaction.atomic
    def put(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        s = ProScheduleUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        items = s.validated_data["items"]

        ProfessionalSchedule.objects.filter(professional=acc.professional).delete()
        for item in items:
            ProfessionalSchedule.objects.create(professional=acc.professional, **item)
        return Response({"message": "График обновлён"})


class ProScheduleExceptionsAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="PRO: список исключений", responses={200: ProScheduleExceptionSerializer(many=True)})
    def get(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        qs = ScheduleException.objects.filter(professional=acc.professional).order_by("-date", "-id")
        return Response({"data": ProScheduleExceptionSerializer(qs, many=True).data})

    @extend_schema(summary="PRO: добавить исключение", request=ProScheduleExceptionCreateSerializer, responses={201: ProScheduleExceptionSerializer})
    def post(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        s = ProScheduleExceptionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = ScheduleException.objects.create(professional=acc.professional, **s.validated_data)
        return Response({"data": ProScheduleExceptionSerializer(obj).data}, status=201)


class ProScheduleExceptionDeleteAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="PRO: удалить исключение", responses={200: MessageResponseSerializer, 404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND])})
    def delete(self, request, exception_id: int):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err
        deleted, _ = ScheduleException.objects.filter(id=exception_id, professional=acc.professional).delete()
        if not deleted:
            return Response(api_error(error="not_found", message="Не найдено"), status=404)
        return Response({"message": "Удалено"})


class ProBookingsAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="PRO: список записей профессионала",
        parameters=[
            OpenApiParameter(name="from", type=str, location=OpenApiParameter.QUERY, required=False, description="YYYY-MM-DD"),
            OpenApiParameter(name="to", type=str, location=OpenApiParameter.QUERY, required=False, description="YYYY-MM-DD"),
        ],
        responses={200: ProBookingSerializer(many=True)},
    )
    def get(self, request):
        acc, err = _get_pro_account_or_unauthorized(request=request)
        if err:
            return err

        qs = Booking.objects.filter(professional=acc.professional).select_related("client").order_by("booking_date", "booking_time")

        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")
        if raw_from:
            try:
                qs = qs.filter(booking_date__gte=timezone.datetime.fromisoformat(raw_from).date())
            except Exception:
                pass
        if raw_to:
            try:
                qs = qs.filter(booking_date__lte=timezone.datetime.fromisoformat(raw_to).date())
            except Exception:
                pass

        return Response({"data": ProBookingSerializer(qs, many=True).data})


def _create_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
    }


def health(request):
    return JsonResponse({"status": "ok", "release": getattr(settings, "RELEASE", "dev")})


class DefaultPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    page_query_param = "page"
    max_page_size = 50

    def paginate_queryset(self, queryset, request, view=None):
        """Paginate only if client explicitly asked for it (page and/or limit).

        Product requirement: return full list by default.
        """

        has_limit = request.query_params.get(self.page_size_query_param) is not None
        has_page = request.query_params.get(self.page_query_param) is not None
        if not (has_limit or has_page):
            return None
        return super().paginate_queryset(queryset, request, view=view)

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


def _organization_name_map() -> dict[int, str]:
    # legacy helper left for backward compatibility; prefer Organization model.
    return dict(Organization.objects.values_list("id", "name"))


class SpecialistListAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Список специализаций",
        auth=[],
        responses={
            200: SpecialistsListResponseSerializer,
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        qs = Specialist.objects.filter(is_active=True).order_by("sort_order", "id")
        return Response({"data": SpecialistSerializer(qs, many=True, context={"request": request}).data})


class ProfessionalListAPIViewLegacy(CsrfExemptAPIView):
    pagination_class = DefaultPagination

    def _parse_availability_limit(self, request) -> int:
        """How many slot times to include in list endpoints.

        - default: 3 (compact preview)
        - availability_limit=0 => include all
        - availability_limit=N => include first N
        """

        raw = request.query_params.get("availability_limit")
        if raw is None or raw == "":
            return 3
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return 3
        return max(0, min(v, 200))

    def _parse_specialist_ids(self, request):
        values = []

        raw_single = request.query_params.get("specialist_id")
        if raw_single:
            values.append(raw_single)

        values.extend(request.query_params.getlist("specialist_id"))

        raw_multi = request.query_params.get("specialist_ids")
        if raw_multi:
            values.extend([x.strip() for x in raw_multi.split(",") if x.strip()])

        ids = []
        for value in values:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(ids))

    def _parse_service_ids(self, request):
        values = []
        raw_single = request.query_params.get("service_id")
        if raw_single:
            values.append(raw_single)

        values.extend(request.query_params.getlist("service_id"))

        raw_multi = request.query_params.get("service_ids")
        if raw_multi:
            values.extend([x.strip() for x in raw_multi.split(",") if x.strip()])

        ids = []
        for value in values:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(set(ids))

    def _parse_organization_id(self, request):
        raw = request.query_params.get("organization_id")
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _search_professional_ids_in_es(
        self, *, search: str, specialist_ids: list[int], service_ids: list[int]
    ):
        if not settings.ES_ENABLED or not search.strip():
            return None

        must_filters = []
        if specialist_ids:
            must_filters.append(
                {
                    "terms": {
                        "specialist_ids": specialist_ids,
                    }
                }
            )
        if service_ids:
            must_filters.append({"terms": {"service_ids": service_ids}})

        payload = {
            "size": 200,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": search,
                                "fields": [
                                    "full_name^3",
                                    "primary_specialty",
                                    "specialties",
                                    "services",
                                ],
                                "type": "best_fields",
                                "operator": "and",
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": must_filters,
                }
            },
        }

        try:
            response = requests.post(
                f"{settings.ES_URL.rstrip('/')}/{settings.ES_DOCTORS_INDEX}/_search",
                json=payload,
                timeout=settings.ES_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            hits = response.json().get("hits", {}).get("hits", [])
            # IMPORTANT:
            # ES анализатор может не находить подстроки/префиксы (например, запрос "Сур" не матчится к "Сурапбеков").
            # Чтобы поиск на фронте всегда работал, если ES ничего не нашёл — делаем fallback на DB поиск.
            if not hits:
                return None
            ids = []
            for hit in hits:
                source = hit.get("_source", {})
                doc_id = source.get("id")
                if doc_id is not None:
                    ids.append(int(doc_id))
            return ids
        except Exception:
            # ES optional: if unavailable, fallback to DB search
            return None

    @extend_schema(
        summary="Список врачей (карточки)",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="specialist_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Фильтр по специализации. Можно передать несколько раз: "
                    "?specialist_id=1&specialist_id=7"
                ),
            ),
            OpenApiParameter(
                name="specialist_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по нескольким специализациям (CSV), например: 1,7,10",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Поиск по ФИО врача и названиям специализаций",
            ),
            OpenApiParameter(
                name="service_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по услуге специалиста",
            ),
            OpenApiParameter(
                name="service_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по нескольким услугам (CSV), например: 1,2,7",
            ),
            OpenApiParameter(
                name="organization_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по организации",
            ),
            OpenApiParameter(
                name="availability_limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Сколько слотов времени вернуть в превью. По умолчанию 3. 0 = все.",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Номер страницы (default: 1)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Количество на странице (default: 10, max: 50)",
            ),
        ],
        responses={
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        base_qs = Professional.objects.filter(is_active=True)
        qs = base_qs.select_related("primary_specialist").prefetch_related(
            "professional_specialties__specialist",
            "services",
        )

        specialist_ids = self._parse_specialist_ids(request)
        service_ids = self._parse_service_ids(request)
        organization_id = self._parse_organization_id(request)
        search = (request.query_params.get("search") or "").strip()
        es_ids = None

        if specialist_ids:
            qs = qs.filter(
                Q(primary_specialist_id__in=specialist_ids)
                | Q(professional_specialties__specialist_id__in=specialist_ids)
            )

        if service_ids:
            qs = qs.filter(
                Q(
                    professional_services__service_id__in=service_ids,
                    professional_services__is_active=True,
                    professional_services__service__is_active=True,
                )
                | Q(legacy_services__id__in=service_ids, legacy_services__is_active=True)
            )

        if organization_id:
            qs = qs.filter(branches__organization_id=organization_id)

        if search:
            es_ids = self._search_professional_ids_in_es(
                search=search,
                specialist_ids=specialist_ids,
                service_ids=service_ids,
            )
            if es_ids is not None:
                if not es_ids:
                    qs = qs.none()
                else:
                    # rebuild queryset without join-produced duplicates,
                    # then apply ES relevance ordering.
                    ordering = Case(
                        *[When(id=pk, then=pos) for pos, pk in enumerate(es_ids)],
                        output_field=IntegerField(),
                    )
                    qs = qs.filter(id__in=es_ids).order_by(ordering)
            else:
                qs = qs.filter(
                    Q(full_name__icontains=search)
                    | Q(professional_specialties__specialist__title__icontains=search)
                    | Q(primary_specialist__title__icontains=search)
                    | Q(professional_services__service__name__icontains=search)
                    | Q(legacy_services__name__icontains=search)
                )

        qs = qs.distinct()

        paginator = self.pagination_class()
        if not search or es_ids is None:
            qs = qs.order_by("id")
        page = paginator.paginate_queryset(qs, request)
        items = page if page is not None else qs

        data = []
        availability_limit = self._parse_availability_limit(request)
        for professional in items:
            day = professional.get_first_available_day(days=30)
            availability = {"label": "", "slots": [], "more_count": 0}
            if day:
                slots = day["times"] if availability_limit == 0 else day["times"][:availability_limit]
                availability = {
                    "label": label_for_day(day["date"]),
                    "slots": slots,
                    "more_count": max(0, len(day["times"]) - len(slots)),
                }
            data.append(
                ProfessionalPreviewSerializer(professional, context={"request": request}).data
                | {"availability": availability}
            )

        if page is None:
            return Response({"data": data})
        return paginator.get_paginated_response(data)


class ProfessionalSearchAPIViewLegacy(ProfessionalListAPIViewLegacy):
    @extend_schema(
        summary="Поиск специалистов (legacy format)",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="query",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Поиск по ФИО специалиста и названиям специализаций",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Номер страницы (default: 1)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Количество на странице (default: 10, max: 50)",
            ),
        ],
        responses={
            200: ProfessionalsListResponseSerializerLegacy,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        mutable_params = request.query_params.copy()
        search = mutable_params.get("query", "").strip()
        if not search:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"query": ["Обязательный параметр"]},
                ),
                status=400,
            )
        mutable_params["search"] = search
        request._request.GET = mutable_params
        return super().get(request)


class ProfessionalFilterAPIViewLegacy(ProfessionalListAPIViewLegacy):
    @extend_schema(
        summary="Фильтр специалистов по специализациям (legacy format)",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="specialist_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Фильтр по нескольким специализациям (CSV), например: 1,7,10",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Номер страницы (default: 1)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Количество на странице (default: 10, max: 50)",
            ),
        ],
        responses={
            200: ProfessionalsListResponseSerializerLegacy,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        mutable_params = request.query_params.copy()
        specialist_ids = mutable_params.get("specialist_ids", "").strip()
        if not specialist_ids:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"specialist_ids": ["Обязательный параметр"]},
                ),
                status=400,
            )
        mutable_params["specialist_ids"] = specialist_ids
        request._request.GET = mutable_params
        return super().get(request)


class ProfessionalListAPIView(ProfessionalListAPIViewLegacy):
    @extend_schema(
        summary="Список специалистов (все категории)",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="specialist_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Фильтр по специализации. Можно передать несколько раз: "
                    "?specialist_id=1&specialist_id=7"
                ),
            ),
            OpenApiParameter(
                name="specialist_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по нескольким специализациям (CSV), например: 1,7,10",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Поиск по ФИО специалиста и названиям специализаций",
            ),
            OpenApiParameter(
                name="service_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по услуге специалиста",
            ),
            OpenApiParameter(
                name="service_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по нескольким услугам (CSV), например: 1,2,7",
            ),
            OpenApiParameter(
                name="organization_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по организации",
            ),
            OpenApiParameter(
                name="availability_limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Сколько слотов времени вернуть в превью. По умолчанию 3. 0 = все.",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Номер страницы (default: 1)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Количество на странице (default: 10, max: 50)",
            ),
        ],
        responses={
            200: ProfessionalsListResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        return super().get(request)


class ProfessionalSearchAPIView(ProfessionalSearchAPIViewLegacy):
    @extend_schema(
        summary="Поиск специалистов (alias для /professionals)",
        auth=[],
        responses={
            200: ProfessionalsListResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        return super().get(request)


class ProfessionalFilterAPIView(ProfessionalListAPIViewLegacy):
    @extend_schema(
        summary="Фильтр специалистов (alias для /professionals)",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="specialist_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="CSV специализаций. Если не передать — вернётся обычный список специалистов.",
            ),
            OpenApiParameter(
                name="service_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по услуге",
            ),
            OpenApiParameter(
                name="service_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="CSV услуг",
            ),
            OpenApiParameter(
                name="organization_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по организации",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Поиск",
            ),
            OpenApiParameter(name="page", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="limit", type=int, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: ProfessionalsListResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        # This endpoint should be usable without required params.
        # If specialist_ids is missing, we behave like /professionals.
        specialist_ids = (request.query_params.get("specialist_ids") or "").strip()
        if specialist_ids:
            return super().get(request)
        return ProfessionalListAPIViewLegacy.get(self, request)


class ProfessionalDetailAPIViewLegacy(CsrfExemptAPIView):
    @extend_schema(
        summary="Детали специалиста (legacy format)",
        auth=[],
        responses={
            200: ProfessionalDetailResponseSerializer,
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request, professional_id: int):
        try:
            professional = (
                Professional.objects.filter(is_active=True)
                .select_related("primary_specialist")
                .prefetch_related(
                    "services",
                    "professional_specialties__specialist",
                    "branches",
                )
                .get(id=professional_id)
            )
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        return Response(
            {"data": ProfessionalDetailSerializer(professional, context={"request": request}).data}
        )


class ProfessionalDetailAPIView(ProfessionalDetailAPIViewLegacy):
    @extend_schema(
        summary="Детали специалиста",
        auth=[],
        responses={
            200: ProfessionalDetailResponseSerializer,
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, professional_id: int):
        return super().get(request, professional_id=professional_id)


class ProfessionalCalendarAPIViewLegacy(CsrfExemptAPIView):
    @extend_schema(
        summary="Календарь специалиста на 30 дней (legacy format)",
        auth=[],
        responses={
            200: ProfessionalCalendarResponseSerializer,
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request, professional_id: int):
        try:
            professional = Professional.objects.get(id=professional_id, is_active=True)
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        return Response({"data": professional.get_calendar(days=30)})


class ProfessionalCalendarAPIView(ProfessionalCalendarAPIViewLegacy):
    @extend_schema(
        summary="Календарь специалиста на 30 дней",
        auth=[],
        responses={
            200: ProfessionalCalendarResponseSerializer,
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, professional_id: int):
        # Optional filter: hide start times where the whole duration doesn't fit.
        # Accept either:
        #  - duration_min=90
        #  - service_ids=1,2,3 (sum duration_min of these services)
        duration_min = request.query_params.get("duration_min")
        if duration_min is None:
            raw = (request.query_params.get("service_ids") or "").strip()
            if raw:
                try:
                    ids = [int(x) for x in raw.split(",") if x.strip()]
                    if ids:
                        duration_min = (
                            Service.objects.filter(id__in=ids, is_active=True)
                            .values_list("duration_min", flat=True)
                        )
                        duration_min = sum(int(x) for x in duration_min)
                except Exception:
                    duration_min = None

        try:
            duration_min_int = int(duration_min) if duration_min is not None else None
        except (TypeError, ValueError):
            duration_min_int = None

        try:
            professional = Professional.objects.get(id=professional_id, is_active=True)
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        return Response({"data": professional.get_calendar(days=30, duration_min=duration_min_int)})


class ProfessionalAvailableServicesAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Услуги специалиста, доступные для старта в выбранную дату и время",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="YYYY-MM-DD",
            ),
            OpenApiParameter(
                name="time",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="HH:MM",
            ),
        ],
        responses={
            200: ProfessionalAvailableServicesResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
        },
    )
    def get(self, request, professional_id: int):
        """Return services that fit into free consecutive slots starting from date+time.

        Frontend use-case:
        - user selects date+time first
        - then frontend shows only services that can start at that moment (duration fits)
        """

        raw_date = (request.query_params.get("date") or "").strip()
        raw_time = (request.query_params.get("time") or "").strip()

        try:
            d = timezone.datetime.fromisoformat(raw_date).date()
        except Exception:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"date": ["Формат YYYY-MM-DD"]},
                ),
                status=400,
            )

        try:
            t = timezone.datetime.strptime(raw_time, "%H:%M").time()
        except Exception:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"time": ["Формат HH:MM"]},
                ),
                status=400,
            )

        try:
            professional = Professional.objects.get(id=professional_id, is_active=True)
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        # Calculate free slots for that date (no duration filter here)
        free_slots = set(professional._get_free_slots_for_date(d))
        start_str = t.strftime("%H:%M")
        if start_str not in free_slots:
            return Response({"data": []})

        slot_minutes = professional.slot_duration_min or 30

        # List services offered by this professional (same filter as booking creation)
        services = list(
            Service.objects.filter(
                Q(professional_services__professional=professional, professional_services__is_active=True)
                | Q(professional=professional),
                is_active=True,
            )
            .distinct()
            .order_by("sort_order", "id")
        )

        def _add_minutes(hhmm: str, minutes: int) -> str:
            h, m = hhmm.split(":")
            base = int(h) * 60 + int(m)
            total = base + minutes
            return f"{total // 60:02d}:{total % 60:02d}"

        allowed = []
        for svc in services:
            duration = int(svc.duration_min or slot_minutes)
            required_slots = max(1, duration // slot_minutes + (1 if duration % slot_minutes else 0))
            ok = True
            for i in range(required_slots):
                if _add_minutes(start_str, slot_minutes * i) not in free_slots:
                    ok = False
                    break
            if ok:
                allowed.append(svc)

        return Response({"data": ServiceSerializer(allowed, many=True, context={"request": request}).data})


class ProfessionalAvailableTimesAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Время специалиста, доступное для выбранных услуг на конкретную дату",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="YYYY-MM-DD",
            ),
            OpenApiParameter(
                name="service_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="CSV услуг, например 19,21",
            ),
        ],
        responses={
            200: ProfessionalAvailableTimesResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
        },
    )
    def get(self, request, professional_id: int):
        """Return start times that fit the duration of selected services.

        This is an explicit alternative to /calendar?service_ids=...
        
        Frontend use-case:
        - user selects services first
        - then frontend shows only available times for that service set
        """

        raw_date = (request.query_params.get("date") or "").strip()
        raw_service_ids = (request.query_params.get("service_ids") or "").strip()

        try:
            d = timezone.datetime.fromisoformat(raw_date).date()
        except Exception:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"date": ["Формат YYYY-MM-DD"]},
                ),
                status=400,
            )

        try:
            service_ids = [int(x) for x in raw_service_ids.split(",") if x.strip()]
        except Exception:
            service_ids = []

        if not service_ids:
            return Response(
                api_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"service_ids": ["Должен быть CSV список id услуг"]},
                ),
                status=400,
            )

        try:
            professional = Professional.objects.get(id=professional_id, is_active=True)
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        # Validate services exist and are allowed for this professional
        services = list(
            Service.objects.filter(
                Q(professional_services__professional=professional, professional_services__is_active=True)
                | Q(professional=professional),
                id__in=service_ids,
                is_active=True,
            ).distinct()
        )
        if len(services) != len(set(service_ids)):
            return Response(
                api_error(
                    error="services_not_found",
                    message="Некоторые услуги не найдены",
                    details={"service_ids": ["Некоторые услуги не найдены или не привязаны к специалисту"]},
                ),
                status=400,
            )

        duration_min = sum(int(s.duration_min or 0) for s in services) or (professional.slot_duration_min or 30)

        # Use existing calendar engine to filter starts by duration
        times = professional._get_free_slots_for_date(d, duration_min=duration_min)

        return Response(
            {
                "date": d.isoformat(),
                "duration_min": int(duration_min),
                "times": times,
            }
        )


class ProfessionalReviewsAPIViewLegacy(CsrfExemptAPIView):
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
        summary="Отзывы специалиста (публичные, legacy format)",
        auth=[],
        responses={
            200: ReviewsPaginatedResponseSerializer,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR],
            ),
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request, professional_id: int):
        if not Professional.objects.filter(id=professional_id, is_active=True).exists():
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        qs = Review.objects.filter(professional_id=professional_id, is_approved=True).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        items = page if page is not None else qs
        if page is None:
            return Response({"data": ReviewSerializer(items, many=True).data})
        return paginator.get_paginated_response(ReviewSerializer(items, many=True).data)

    @extend_schema(
        summary="Оставить отзыв (требует авторизации)",
        request=CreateReviewSerializer,
        responses={
            201: OpenApiResponse(description="Отзыв отправлен на модерацию"),
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR, EX_CLIENT_NOT_FOUND, EX_CANNOT_REVIEW],
            ),
            401: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_AUTHENTICATED],
            ),
            403: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_FORBIDDEN],
            ),
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def post(self, request, professional_id: int):
        s = CreateReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        booking_id = s.validated_data["booking_id"]
        rating = s.validated_data["rating"]
        text = s.validated_data.get("text", "")

        try:
            client = Client.objects.get(user=request.user)
        except Client.DoesNotExist:
            return Response(api_error(error="client_not_found", message="Клиент не найден"), status=400)

        try:
            booking = Booking.objects.get(id=booking_id, client=client, professional_id=professional_id)
        except Booking.DoesNotExist:
            return Response(api_error(error="not_found", message="Запись не найдена"), status=404)

        if booking.status != "completed":
            return Response(
                api_error(
                    error="cannot_review",
                    message="Оставить отзыв можно только после завершённого приёма",
                ),
                status=400,
            )

        Review.objects.create(
            professional_id=professional_id,
            client=client,
            booking=booking,
            rating=int(rating),
            text=text,
            is_approved=False,
        )
        return Response({"message": "Отзыв отправлен на модерацию"}, status=201)


class ProfessionalReviewsAPIView(ProfessionalReviewsAPIViewLegacy):
    @extend_schema(
        summary="Отзывы специалиста (публичные)",
        auth=[],
        responses={
            200: ReviewsPaginatedResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, professional_id: int):
        return super().get(request, professional_id=professional_id)

    @extend_schema(
        summary="Оставить отзыв специалисту (требует авторизации)",
        request=CreateReviewSerializer,
        responses={
            201: OpenApiResponse(description="Отзыв отправлен на модерацию"),
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_VALIDATION_ERROR, EX_CLIENT_NOT_FOUND, EX_CANNOT_REVIEW],
            ),
            401: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_AUTHENTICATED]),
            403: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_FORBIDDEN]),
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def post(self, request, professional_id: int):
        return super().post(request, professional_id=professional_id)


class ServiceListAPIView(CsrfExemptAPIView):
    pagination_class = DefaultPagination

    @extend_schema(
        summary="Список услуг",
        auth=[],
        parameters=[
            OpenApiParameter(name="professional_id", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="specialist_id", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="organization_id", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="search", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="page", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="limit", type=int, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: ServicesListResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        qs = Service.objects.filter(is_active=True).prefetch_related("professionals")

        professional_id = request.query_params.get("professional_id")
        if professional_id:
            try:
                pid = int(professional_id)
                qs = qs.filter(
                    Q(professional_id=pid)
                    | Q(
                        professional_services__professional_id=pid,
                        professional_services__is_active=True,
                    )
                )
            except ValueError:
                return Response(
                    api_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"professional_id": ["Должно быть целым числом"]},
                    ),
                    status=400,
                )

        specialist_id = request.query_params.get("specialist_id")
        if specialist_id:
            try:
                sid = int(specialist_id)
                qs = qs.filter(
                    Q(professionals__professional_specialties__specialist_id=sid)
                    | Q(professional__professional_specialties__specialist_id=sid)
                )
            except ValueError:
                return Response(
                    api_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"specialist_id": ["Должно быть целым числом"]},
                    ),
                    status=400,
                )

        organization_id = request.query_params.get("organization_id")
        if organization_id:
            try:
                org_id = int(organization_id)
            except ValueError:
                return Response(
                    api_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"organization_id": ["Должно быть целым числом"]},
                    ),
                    status=400,
                )

            qs = qs.filter(
                Q(professionals__branches__organization_id=org_id)
                | Q(professional__branches__organization_id=org_id)
            )

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

        qs = qs.distinct().order_by("sort_order", "id")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        items = page if page is not None else qs

        if page is None:
            return Response({"data": ServiceSerializer(items, many=True, context={"request": request}).data})

        return paginator.get_paginated_response(
            ServiceSerializer(items, many=True, context={"request": request}).data
        )


class OrganizationProfessionalsAPIView(ProfessionalListAPIView):
    @extend_schema(
        summary="Список специалистов организации",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="availability_limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Сколько слотов времени вернуть в превью. По умолчанию 3. 0 = все.",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses={
            200: ProfessionalsListResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, organization_id: int):
        mutable_params = request.query_params.copy()
        mutable_params["organization_id"] = str(organization_id)
        request._request.GET = mutable_params
        return super().get(request)


class OrganizationServicesAPIView(ServiceListAPIView):
    @extend_schema(
        summary="Список услуг организации",
        auth=[],
        responses={
            200: ServicesListResponseSerializer,
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, organization_id: int):
        mutable_params = request.query_params.copy()
        mutable_params["organization_id"] = str(organization_id)
        request._request.GET = mutable_params
        return super().get(request)


class OrganizationsAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Список организаций",
        auth=[],
        responses={
            200: OrganizationsListResponseSerializer,
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        # Stable ordering for frontend (and matches admin expectations): by id.
        orgs = Organization.objects.filter(is_active=True).order_by("id")
        data = []
        for org in orgs:
            professionals_qs = Professional.objects.filter(is_active=True, branches__organization=org)
            specialists_count = (
                professionals_qs.values("professional_specialties__specialist")
                .exclude(professional_specialties__specialist__isnull=True)
                .distinct()
                .count()
            )
            data.append(
                {
                    "id": org.id,
                    "name": org.name,
                    "logo_url": request.build_absolute_uri(org.logo.url) if getattr(org, "logo", None) else "",
                    "paylink_enabled": getattr(org, "paylink_enabled", True),
                    "specialists_count": specialists_count,
                    "professionals_count": professionals_qs.count(),
                }
            )
        return Response({"data": data})


class OrganizationDetailAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Детали организации",
        auth=[],
        responses={
            200: OrganizationDetailResponseSerializer,
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, organization_id: int):
        try:
            org = Organization.objects.get(id=organization_id, is_active=True)
        except Organization.DoesNotExist:
            return Response(api_error(error="not_found", message="Организация не найдена"), status=404)

        qs = Professional.objects.filter(is_active=True, branches__organization=org)
        specialists_count = (
            qs.values("professional_specialties__specialist")
            .exclude(professional_specialties__specialist__isnull=True)
            .distinct()
            .count()
        )

        data = {
            "id": org.id,
            "name": org.name,
            "logo_url": request.build_absolute_uri(org.logo.url) if getattr(org, "logo", None) else "",
            "paylink_enabled": getattr(org, "paylink_enabled", True),
            "specialists_count": specialists_count,
            "professionals_count": qs.count(),
            "services_count": Service.objects.filter(
                Q(professionals__branches__organization=org)
                | Q(professional__branches__organization=org),
                is_active=True,
            ).distinct().count(),
            "branches": [
                {
                    "id": branch.id,
                    "title": branch.title,
                    "address": branch.address,
                    "is_active": branch.is_active,
                }
                for branch in org.branches.filter(is_active=True).order_by("id")
            ],
        }
        return Response({"data": data})


class BranchesAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Список филиалов",
        auth=[],
        responses={
            200: BranchesListResponseSerializer,
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request):
        branches = (
            Branch.objects.filter(is_active=True, organization__is_active=True)
            .select_related("organization")
            # Stable ordering for frontend: by id
            .order_by("id")
        )
        organization_id = request.query_params.get("organization_id")
        if organization_id:
            try:
                branches = branches.filter(organization_id=int(organization_id))
            except ValueError:
                branches = branches.none()
        data = []
        for br in branches:
            professionals_count = Professional.objects.filter(is_active=True, branches=br).count()
            data.append(
                {
                    "id": br.id,
                    "organization_id": br.organization_id,
                    "organization_name": br.organization.name,
                    "title": br.title,
                    "address": br.address,
                    "professionals_count": professionals_count,
                }
            )
        return Response({"data": data})


class BranchDetailAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Детали филиала (включая график работы)",
        auth=[],
        responses={
            200: BranchDetailResponseSerializer,
            404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND]),
        },
    )
    def get(self, request, branch_id: int):
        try:
            br = Branch.objects.select_related("organization").get(id=branch_id, is_active=True)
        except Branch.DoesNotExist:
            return Response(api_error(error="not_found", message="Филиал не найден"), status=404)

        professionals_count = Professional.objects.filter(is_active=True, branches=br).count()
        schedule = (
            BranchSchedule.objects.filter(branch=br)
            .order_by("day_of_week")
            .values(
                "day_of_week",
                "is_working",
                "start_time",
                "end_time",
                "break_start",
                "break_end",
            )
        )

        data = {
            "id": br.id,
            "organization_id": br.organization_id,
            "organization_name": br.organization.name,
            "title": br.title,
            "address": br.address,
            "professionals_count": professionals_count,
            "schedule": list(schedule),
        }
        return Response({"data": data})


class BranchProfessionalsAPIView(ProfessionalListAPIViewLegacy):
    @extend_schema(
        summary="Список специалистов филиала",
        auth=[],
        parameters=[
            OpenApiParameter(
                name="specialist_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Фильтр по специализации (id). Можно передавать также specialist_ids=1,2,3",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Поиск по ФИО/специализациям/услугам",
            ),
            OpenApiParameter(
                name="availability_limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Сколько слотов времени вернуть в превью. По умолчанию 3. 0 = все.",
            ),
            OpenApiParameter(name="page", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="limit", type=int, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: ProfessionalsListResponseSerializer},
    )
    def get(self, request, branch_id: int):
        if not Branch.objects.filter(id=branch_id, is_active=True).exists():
            return Response(api_error(error="not_found", message="Филиал не найден"), status=404)

        # reuse ProfessionalListAPIViewLegacy rendering but filter base queryset by branch
        base_qs = Professional.objects.filter(is_active=True, branches__id=branch_id)
        qs = base_qs.select_related("primary_specialist").prefetch_related(
            "professional_specialties__specialist",
            "services",
        )

        specialist_ids = self._parse_specialist_ids(request)
        service_ids = self._parse_service_ids(request)
        search = (request.query_params.get("search") or "").strip()
        es_ids = None

        if specialist_ids:
            qs = qs.filter(
                Q(primary_specialist_id__in=specialist_ids)
                | Q(professional_specialties__specialist_id__in=specialist_ids)
            )

        if service_ids:
            qs = qs.filter(
                Q(
                    professional_services__service_id__in=service_ids,
                    professional_services__is_active=True,
                    professional_services__service__is_active=True,
                )
                | Q(legacy_services__id__in=service_ids, legacy_services__is_active=True)
            )

        if search:
            es_ids = self._search_professional_ids_in_es(
                search=search,
                specialist_ids=specialist_ids,
                service_ids=service_ids,
            )
            if es_ids is not None:
                if not es_ids:
                    qs = qs.none()
                else:
                    ordering = Case(
                        *[When(id=pk, then=pos) for pos, pk in enumerate(es_ids)],
                        output_field=IntegerField(),
                    )
                    qs = qs.filter(id__in=es_ids).order_by(ordering)
            else:
                qs = qs.filter(
                    Q(full_name__icontains=search)
                    | Q(professional_specialties__specialist__title__icontains=search)
                    | Q(primary_specialist__title__icontains=search)
                    | Q(professional_services__service__name__icontains=search)
                    | Q(legacy_services__name__icontains=search)
                )

        qs = qs.distinct()

        paginator = self.pagination_class()
        if not search or es_ids is None:
            qs = qs.order_by("id")
        page = paginator.paginate_queryset(qs, request)
        items = page if page is not None else qs

        data = []
        availability_limit = self._parse_availability_limit(request)
        for professional in items:
            day = professional.get_first_available_day(days=30)
            availability = {"label": "", "slots": [], "more_count": 0}
            if day:
                slots = day["times"] if availability_limit == 0 else day["times"][:availability_limit]
                availability = {
                    "label": label_for_day(day["date"]),
                    "slots": slots,
                    "more_count": max(0, len(day["times"]) - len(slots)),
                }
            data.append(
                ProfessionalPreviewSerializer(professional, context={"request": request}).data
                | {"availability": availability}
            )

        if page is None:
            return Response({"data": data})
        return paginator.get_paginated_response(data)


class BranchSpecialistsAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Специализации филиала",
        auth=[],
        responses={200: SpecialistsListResponseSerializer, 404: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_NOT_FOUND])},
    )
    def get(self, request, branch_id: int):
        try:
            br = Branch.objects.get(id=branch_id, is_active=True)
        except Branch.DoesNotExist:
            return Response(api_error(error="not_found", message="Филиал не найден"), status=404)
        qs = br.specialists.filter(is_active=True).order_by("sort_order", "id")
        return Response({"data": SpecialistSerializer(qs, many=True, context={"request": request}).data})


class OrganizationBranchesAPIView(BranchesAPIView):
    @extend_schema(
        summary="Список филиалов организации",
        auth=[],
        responses={
            200: BranchesListResponseSerializer,
            500: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_SERVER_ERROR]),
        },
    )
    def get(self, request, organization_id: int):
        mutable_params = request.query_params.copy()
        mutable_params["organization_id"] = str(organization_id)
        request._request.GET = mutable_params
        return super().get(request)


class FeatureFlagsAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Фичи проекта: филиалы и paylink",
        auth=[],
        responses={
            200: FeatureFlagsSerializer,
        },
    )
    def get(self, request):
        feature_settings = ProjectFeatureSettings.objects.order_by("id").first()
        branches_enabled = bool(getattr(settings, "FEATURE_BRANCHES_ENABLED", True))
        paylink_enabled = bool(getattr(settings, "FEATURE_PAYLINK_ENABLED", True))
        if feature_settings:
            branches_enabled = feature_settings.branches_enabled
            paylink_enabled = feature_settings.paylink_enabled
        return Response(
            {
                "branches_enabled": branches_enabled,
                "paylink_enabled": paylink_enabled,
                # capabilities: whether per-entity toggles are supported by backend
                "paylink_by_organization": True,
                "paylink_by_professional": True,
            }
        )



def _is_paylink_enabled_for_professional(*, professional: Professional) -> bool:
    """Effective paylink state: global AND organization AND professional."""

    feature_settings = ProjectFeatureSettings.objects.order_by("id").first()
    global_enabled = bool(getattr(settings, "FEATURE_PAYLINK_ENABLED", True))
    if feature_settings is not None:
        global_enabled = global_enabled and bool(feature_settings.paylink_enabled)

    org_enabled = True
    if professional.branches.exists():
        org_enabled = any(b.organization.paylink_enabled for b in professional.branches.select_related("organization") if b.organization)

    return bool(global_enabled and org_enabled and getattr(professional, "paylink_enabled", True))

class SendOtpAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Отправить OTP",
        auth=[],
        request=SendOtpSerializer,
        responses={
            200: SendOtpResponseSerializer,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_INVALID_PHONE, EX_VALIDATION_ERROR],
            ),
            429: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_TOO_MANY_REQUESTS],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def post(self, request):
        s = SendOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalize_phone(s.validated_data["phone"])

        if not is_supported_phone(phone):
            return Response(
                api_error(error="invalid_phone", message="Неверный формат телефона"),
                status=400,
            )

        existing = (
            SMSCode.objects.filter(
                phone_number=phone,
                purpose=SMSCode.PURPOSE_LOGIN,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )
        if existing:
            cooldown_until = existing.created_at + timedelta(
                seconds=settings.OTP_RESEND_COOLDOWN
            )
            if cooldown_until > timezone.now():
                retry_after = int((cooldown_until - timezone.now()).total_seconds())
                return Response(
                    api_error(
                        error="too_many_requests",
                        message="Подождите 60 секунд перед повторной отправкой",
                        details={"retry_after": retry_after},
                    ),
                    status=429,
                )

        last_code = (
            SMSCode.objects.filter(
                phone_number=phone,
                purpose=SMSCode.PURPOSE_LOGIN,
            )
            .order_by("-created_at")
            .first()
        )
        if last_code and last_code.attempts >= settings.OTP_MAX_ATTEMPTS:
            block_until = last_code.created_at + timedelta(
                seconds=settings.OTP_BLOCK_SECONDS
            )
            if block_until > timezone.now():
                retry_after = int((block_until - timezone.now()).total_seconds())
                return Response(
                    api_error(
                        error="too_many_requests",
                        message="Слишком много неверных попыток. Запросите новый код позже.",
                        details={"retry_after": retry_after},
                    ),
                    status=429,
                )

        # Максимум 3 отправки в час на один номер
        one_hour_ago = timezone.now() - timedelta(hours=1)
        sends_last_hour = SMSCode.objects.filter(
            phone_number=phone,
            purpose=SMSCode.PURPOSE_LOGIN,
            created_at__gte=one_hour_ago,
        ).count()
        if sends_last_hour >= settings.OTP_MAX_SENDS_PER_HOUR:
            return Response(
                api_error(
                    error="too_many_requests",
                    message="Превышен лимит отправок. Попробуйте через час.",
                    details={"retry_after": 3600},
                ),
                status=429,
            )

        if settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE:
            code = settings.DEV_OTP_CODE
        else:
            code = f"{random.randint(0, 999999):06d}"

        expires_at = timezone.now() + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)
        SMSCode.objects.create(
            phone_number=phone,
            code=code,
            purpose=SMSCode.PURPOSE_LOGIN,
            payload={"flow": "phone"},
            expires_at=expires_at,
        )

        payload = {"message": "Код отправлен", "expires_in": settings.OTP_EXPIRE_SECONDS}
        if settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE:
            payload["dev_code"] = code
        
        # Реальная отправка SMS (если не dev bypass)
        if not (settings.DEV_OTP_BYPASS and phone == settings.DEV_OTP_PHONE):
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


class VerifyOtpAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Проверить OTP (шаг 2) и получить registration_token для заполнения профиля (шаг 3)",
        auth=[],
        request=VerifyOtpSerializer,
        responses={
            200: VerifyOtpResponseSerializer,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_INVALID_PHONE, EX_INVALID_CODE, EX_VALIDATION_ERROR],
            ),
            429: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_TOO_MANY_REQUESTS],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def post(self, request):
        s = VerifyOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalize_phone(s.validated_data["phone"])
        code = s.validated_data["code"]

        if not is_supported_phone(phone):
            return Response(
                api_error(error="invalid_phone", message="Неверный формат телефона"),
                status=400,
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
            # в формате ТЗ: invalid_code + attempts_left
            return Response(
                api_error(
                    error="invalid_code",
                    message="Неверный код",
                    details={"attempts_left": settings.OTP_MAX_ATTEMPTS},
                ),
                status=400,
            )

        block_until = sms.created_at + timedelta(seconds=settings.OTP_BLOCK_SECONDS)
        if sms.attempts >= settings.OTP_MAX_ATTEMPTS and block_until > timezone.now():
            retry_after = max(0, int((block_until - timezone.now()).total_seconds()))
            return Response(
                api_error(
                    error="too_many_requests",
                    message="Слишком много неверных попыток. Запросите новый код.",
                    details={"retry_after": retry_after},
                ),
                status=429,
            )

        if sms.code != code:
            sms.attempts += 1
            sms.save(update_fields=["attempts"])
            attempts_left = max(0, settings.OTP_MAX_ATTEMPTS - sms.attempts)
            return Response(
                api_error(
                    error="invalid_code",
                    message="Неверный код",
                    details={"attempts_left": attempts_left},
                ),
                status=400,
            )

        # OTP is correct.
        # If this user already exists (registered before) -> this is a LOGIN flow:
        # issue token immediately and do NOT require step 3.
        user = User.objects.filter(username=phone).first()
        if user and Client.objects.filter(user=user).exists():
            sms.is_used = True
            sms.save(update_fields=["is_used"])
            tokens = _create_tokens_for_user(user)
            return Response(
                {
                    **tokens,
                    "token_type": "bearer",
                    "needs_profile": False,
                    "is_new_patient": False,
                }
            )

        # New registration flow (no Client exists yet): proceed to step 3.
        # We mark sms as used now because OTP is already validated and we don't want to ask for it again.
        sms.is_used = True
        sms.save(update_fields=["is_used"])

        return Response(
            {
                "phone": phone,
                "message": "OTP подтвержден. Пожалуйста, завершите регистрацию, заполнив профиль.",
                "needs_profile": True,
                "is_new_patient": True,
            }
        )


class CompleteClientProfileAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Завершить регистрацию клиента (шаг 3): заполнить профиль и получить access_token",
        auth=[],
        description=(
            "Обязательное поле: **phone**. Остальные поля опциональны и могут быть пустыми.\n\n"
            "Пустые значения:\n"
            "- строки: можно отправлять \"\" или null\n"
            "- inn/birth_date: можно не отправлять, или отправлять null, или отправлять \"\" (\"\" будет интерпретировано как null)\n"
            "- gender: можно не отправлять, или отправлять null/\"\"\n"
        ),
        request=CompleteClientProfileSerializer,
        responses={
            200: CompleteClientProfileResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_VALIDATION_ERROR]),
            403: OpenApiResponse(response=ApiErrorSerializer, examples=[EX_FORBIDDEN]),
        },
        examples=[
            OpenApiExample(
                name="empty_fields",
                value={
                    "phone": "0700000000",
                    "full_name": "",
                    "inn": "",
                    "birth_date": "",
                    "gender": "",
                    "nickname": "",
                    "telegram": "",
                    "instagram": "",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="only_phone",
                value={"phone": "0700000000"},
                request_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request):
        s = CompleteClientProfileSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        phone = normalize_phone(s.validated_data["phone"])
        user, _ = User.objects.get_or_create(username=phone)
        client, _ = Client.objects.get_or_create(user=user, defaults={"phone": phone})
        client.phone = phone
        client.full_name = (s.validated_data.get("full_name") or "").strip()
        client.inn = s.validated_data.get("inn")
        client.birth_date = s.validated_data.get("birth_date")
        if s.validated_data.get("gender"):
            # GenderInputField already normalizes to 'male'/'female'
            client.gender = s.validated_data["gender"]
        client.nickname = (s.validated_data.get("nickname") or "").strip()
        client.telegram = (s.validated_data.get("telegram") or "").strip()
        client.instagram = (s.validated_data.get("instagram") or "").strip()
        client.save()

        tokens = _create_tokens_for_user(user)
        return Response({**tokens, "token_type": "bearer"})


class BookingCreateAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Создать запись (требует авторизации)",
        request=CreateBookingSerializer,
        responses={
            201: BookingCreateResponseSerializer,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[
                    EX_VALIDATION_ERROR,
                    EX_CLIENT_NOT_FOUND,
                    EX_SERVICES_NOT_FOUND,
                    EX_DATE_IN_PAST,
                ],
            ),
            401: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_AUTHENTICATED],
            ),
            403: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_FORBIDDEN],
            ),
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            409: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SLOT_UNAVAILABLE],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    @transaction.atomic
    def post(self, request):
        s = CreateBookingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            client = Client.objects.get(user=request.user)
        except Client.DoesNotExist:
            return Response(api_error(error="client_not_found", message="Клиент не найден"), status=400)

        # strict registration: block booking until required profile is filled
        if not client.is_profile_completed:
            return Response(
                api_error(
                    error="profile_incomplete",
                    message="Профиль не заполнен",
                    details={"required": ["phone"]},
                ),
                status=403,
            )

        try:
            professional = Professional.objects.get(id=data["professional_id"], is_active=True)
        except Professional.DoesNotExist:
            return Response(api_error(error="not_found", message="Специалист не найден"), status=404)

        services = list(
            Service.objects.filter(
                Q(professional_services__professional=professional, professional_services__is_active=True)
                | Q(professional=professional),
                id__in=data["service_ids"],
                is_active=True,
            ).distinct()
        )
        if len(services) != len(set(data["service_ids"])):
            return Response(api_error(error="services_not_found", message="Некоторые услуги не найдены"), status=400)

        now = bishek_now()
        if data["date"] < now.date():
            return Response(api_error(error="date_in_past", message="Дата записи уже прошла"), status=400)

        if data["date"] == now.date() and data["time"] <= now.time():
            return Response(api_error(error="date_in_past", message="Дата записи уже прошла"), status=400)

        free_slots = professional._get_free_slots_for_date(data["date"])
        requested_time = data["time"].strftime("%H:%M")
        if requested_time not in free_slots:
            return Response(
                api_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                ),
                status=409,
            )

        total_price = sum(svc.price for svc in services)
        total_duration_min = sum(svc.duration_min for svc in services)

        # Проверяем что весь диапазон слотов свободен
        slot_minutes = professional.slot_duration_min or 30
        slots_needed = max(1, total_duration_min // slot_minutes + (1 if total_duration_min % slot_minutes else 0))

        slot_times = []
        start_dt = timezone.datetime.combine(data["date"], data["time"])
        for i in range(slots_needed):
            slot_times.append((start_dt + timedelta(minutes=slot_minutes * i)).time())

        slot_strings = [t.strftime("%H:%M") for t in slot_times]
        if any(t not in free_slots for t in slot_strings):
            return Response(
                api_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                ),
                status=409,
            )

        existing = Booking.objects.filter(
            professional=professional,
            booking_date=data["date"],
        ).exclude(status="cancelled")

        booked = set(existing.values_list("booking_time", flat=True))
        # дополнительно учитываем длительность уже созданных записей
        for b in existing:
            if b.total_duration_min:
                b_slots = max(
                    1,
                    b.total_duration_min // slot_minutes
                    + (1 if b.total_duration_min % slot_minutes else 0),
                )
                b_start = timezone.datetime.combine(b.booking_date, b.booking_time)
                for i in range(b_slots):
                    booked.add((b_start + timedelta(minutes=slot_minutes * i)).time())

        for t in slot_times:
            if t in booked:
                return Response(
                    api_error(
                        error="slot_unavailable",
                        message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                    ),
                    status=409,
                )

        confirmation_code = make_confirmation_code()
        for _ in range(10):
            if not Booking.objects.filter(confirmation_code=confirmation_code).exists():
                break
            confirmation_code = make_confirmation_code()

        booking = Booking.objects.create(
            client=client,
            professional=professional,
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
                    "professional": {
                        "full_name": professional.full_name,
                        "photo_url": ProfessionalPreviewSerializer(
                            professional, context={"request": request}
                        ).data.get("photo_url", ""),
                        "specialty": professional.primary_specialist.title if professional.primary_specialist_id else "",
                        # Keep frontend contract stable
                        "clinic_address": professional.organization_address,
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





class PhoneCountriesAPIView(CsrfExemptAPIView):
    @extend_schema(
        summary="Список стран телефонов",
        auth=[],
        responses={
            200: PhoneCountrySerializer(many=True),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        qs = PhoneCountry.objects.all()
        return Response(PhoneCountrySerializer(qs, many=True, context={"request": request}).data)


class MyBookingsAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Мои записи (требует авторизации)",
        responses={
            200: MyBookingsResponseSerializer,
            401: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_AUTHENTICATED],
            ),
            403: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_FORBIDDEN],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def get(self, request):
        try:
            client = Client.objects.get(user=request.user)
        except Client.DoesNotExist:
            return Response({"data": []})

        qs = Booking.objects.filter(client=client).select_related("professional").order_by("-created_at")
        return Response({"data": BookingItemSerializer(qs, many=True).data})


class CancelBookingAPIView(CsrfExemptAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Отменить запись (требует авторизации)",
        responses={
            200: MessageResponseSerializer,
            400: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_CANNOT_CANCEL, EX_CLIENT_NOT_FOUND, EX_VALIDATION_ERROR],
            ),
            401: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_AUTHENTICATED],
            ),
            403: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_FORBIDDEN],
            ),
            404: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_NOT_FOUND],
            ),
            500: OpenApiResponse(
                response=ApiErrorSerializer,
                examples=[EX_SERVER_ERROR],
            ),
        },
    )
    def delete(self, request, booking_id: int):
        try:
            client = Client.objects.get(user=request.user)
        except Client.DoesNotExist:
            return Response(api_error(error="client_not_found", message="Клиент не найден"), status=400)

        try:
            booking = Booking.objects.get(id=booking_id, client=client)
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
        booking.cancelled_by = "client"
        booking.save(update_fields=["status", "cancelled_by", "updated_at"])
        return Response({"message": "Запись отменена"})
