from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any, Optional

import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from django.db.models import Prefetch, Q

from django.utils import timezone

from django.contrib.auth.models import User

from apps.organizations.models import (
    Branch,
    BranchSchedule,
    Organization,
    Professional,
    ProfessionalSpecialty,
    ProfessionalSchedule,
    ProfessionalService,
    Service,
    ScheduleException,
    Specialist,
    _make_unique_slug,
)

from .graphql_auth import get_user_from_request
from .graphql_bot_auth import require_admin
from .graphql_extensions import RestLikeErrorsExtension, gql_error


def _normalize_and_validate_phone(phone: str) -> str:
    from api.v1.utils import is_supported_phone, normalize_phone

    normalized = normalize_phone(phone or "")
    if not normalized or not is_supported_phone(normalized):
        raise gql_error(
            error="validation_error",
            message="Невалидные данные",
            details={"client_phone": ["Неверный формат телефона"]},
        )
    return normalized


def _get_or_create_client_by_phone(*, phone: str, full_name: str = ""):
    """Bot/admin helper: ensure auth.User + Client exist for given phone."""

    from apps.organizations.models import Client

    normalized = _normalize_and_validate_phone(phone)
    user, _ = User.objects.get_or_create(username=normalized)
    client, created = Client.objects.get_or_create(user=user, defaults={"phone": normalized})
    # keep phone synced (some legacy rows might have empty phone)
    if client.phone != normalized:
        client.phone = normalized
    if full_name:
        client.full_name = (full_name or "").strip()
    if created or full_name:
        client.save()
    return client


def _resolve_services_for_professional(*, professional: Professional, service_ids: list[int]) -> list[Service]:
    """Service resolution compatible with REST.

    - New relation: Professional.services (through ProfessionalService)
    - Legacy relation: Service.professional FK
    """

    ids = [int(x) for x in (service_ids or [])]
    if not ids:
        raise gql_error(
            error="validation_error",
            message="Невалидные данные",
            details={"service_ids": ["Обязательное поле"]},
        )

    services = list(
        Service.objects.filter(
            Q(professional_services__professional=professional, professional_services__is_active=True)
            | Q(professional=professional),
            id__in=ids,
            is_active=True,
        ).distinct()
    )
    if len(services) != len(set(ids)):
        raise gql_error(error="services_not_found", message="Некоторые услуги не найдены")
    return services


def _parse_hhmm_to_time(value: str) -> time:
    try:
        hh, mm = (value or "").split(":")
        return timezone.datetime(2000, 1, 1, int(hh), int(mm)).time()
    except Exception:
        raise gql_error(
            error="validation_error",
            message="Невалидные данные",
            details={"time": ["Ожидается формат HH:MM"]},
        )


def _ensure_slot_available(
    *,
    professional: Professional,
    booking_date: date,
    booking_time: time,
    total_duration_min: int,
    exclude_booking_id: Optional[int] = None,
):
    """Availability check similar to REST, with ability to exclude one booking (for reschedule)."""

    # schedule exception
    exc = professional.schedule_exceptions.filter(date=booking_date).first()
    if exc and exc.is_day_off:
        raise gql_error(error="slot_unavailable", message="Выбранное время недоступно")

    dow = booking_date.weekday()
    schedule = professional.schedule.filter(day_of_week=dow, is_working=True).first()
    start_time = getattr(schedule, "start_time", None)
    end_time = getattr(schedule, "end_time", None)
    break_start = getattr(schedule, "break_start", None)
    break_end = getattr(schedule, "break_end", None)

    if exc and not exc.is_day_off:
        if exc.start_time:
            start_time = exc.start_time
        if exc.end_time:
            end_time = exc.end_time
        # break override can be explicitly set by exception
        break_start = exc.break_start
        break_end = exc.break_end

    if not start_time or not end_time:
        raise gql_error(error="slot_unavailable", message="Выбранное время недоступно")

    slot_minutes = int(getattr(professional, "slot_duration_min", 30) or 30)
    duration = int(total_duration_min or slot_minutes)
    required_slots = max(1, duration // slot_minutes + (1 if duration % slot_minutes else 0))

    # must be aligned to slot grid
    start_min = start_time.hour * 60 + start_time.minute
    bt_min = booking_time.hour * 60 + booking_time.minute
    if bt_min < start_min:
        raise gql_error(error="slot_unavailable", message="Выбранное время недоступно")
    if (bt_min - start_min) % slot_minutes != 0:
        raise gql_error(error="validation_error", message="Невалидные данные", details={"time": ["Время должно совпадать с шагом слотов"]})

    now = timezone.localtime(timezone.now())
    if booking_date == now.date() and booking_time <= now.time():
        raise gql_error(error="date_in_past", message="Дата записи уже прошла")

    start_dt = timezone.datetime.combine(booking_date, booking_time)
    end_dt = start_dt + timedelta(minutes=slot_minutes * required_slots)
    work_end_dt = timezone.datetime.combine(booking_date, end_time)
    if end_dt > work_end_dt:
        raise gql_error(error="slot_unavailable", message="Выбранное время недоступно")

    slot_times = [(start_dt + timedelta(minutes=slot_minutes * i)).time() for i in range(required_slots)]
    if break_start and break_end:
        for t in slot_times:
            if break_start <= t < break_end:
                raise gql_error(error="slot_unavailable", message="Выбранное время недоступно")

    # collision check
    from apps.organizations.models import Booking

    existing = Booking.objects.filter(professional=professional, booking_date=booking_date).exclude(status="cancelled")
    if exclude_booking_id is not None:
        existing = existing.exclude(id=int(exclude_booking_id))

    booked = set(existing.values_list("booking_time", flat=True))
    for b in existing.only("booking_date", "booking_time", "total_duration_min"):
        b_duration = int(b.total_duration_min or slot_minutes)
        b_slots = max(1, b_duration // slot_minutes + (1 if b_duration % slot_minutes else 0))
        b_start = timezone.datetime.combine(b.booking_date, b.booking_time)
        for i in range(b_slots):
            booked.add((b_start + timedelta(minutes=slot_minutes * i)).time())

    if any(t in booked for t in slot_times):
        raise gql_error(
            error="slot_unavailable",
            message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
        )


@strawberry.type
class SpecialistType:
    id: strawberry.ID
    title: str
    slug: str
    description: str
    is_active: bool
    sort_order: int

    @strawberry.field
    def icon_url(self) -> str:
        from api.v1.utils import public_absolute_url

        raw = getattr(self._obj, "icon_url", None)
        if not raw:
            return ""
        # ImageField
        if hasattr(raw, "url"):
            return public_absolute_url(raw.url)
        # string stored in DB
        return public_absolute_url(str(raw))


@strawberry.type
class BookingType:
    id: strawberry.ID
    confirmation_code: str
    status: str
    booking_date: date
    booking_time: time
    total_price: Optional[int]

    @strawberry.field
    def professional_name(self) -> str:
        return self._obj.professional.full_name if self._obj.professional_id else ""


@strawberry.type
class BookingAdminType:
    """Booking view for admin/bot usage."""

    id: strawberry.ID
    confirmation_code: str
    status: str
    booking_date: date
    booking_time: time
    total_price: Optional[int]

    client_phone: str
    client_full_name: str

    professional_id: int
    professional_name: str

    branch_id: Optional[int]
    organization_id: Optional[int]

    @staticmethod
    def from_obj(obj) -> "BookingAdminType":
        prof = getattr(obj, "professional", None)
        client = getattr(obj, "client", None)
        branch = getattr(obj, "branch", None)
        return BookingAdminType(
            id=str(obj.id),
            confirmation_code=getattr(obj, "confirmation_code", ""),
            status=getattr(obj, "status", ""),
            booking_date=obj.booking_date,
            booking_time=obj.booking_time,
            total_price=getattr(obj, "total_price", None),
            client_phone=(getattr(client, "phone", "") or "") if client else "",
            client_full_name=(getattr(client, "full_name", "") or "") if client else "",
            professional_id=int(getattr(obj, "professional_id", 0) or 0),
            professional_name=(getattr(prof, "full_name", "") or "") if prof else "",
            branch_id=int(getattr(obj, "branch_id", 0) or 0) or None,
            organization_id=int(getattr(branch, "organization_id", 0) or 0) if branch else None,
        )


@strawberry.type
class OrganizationType:
    id: strawberry.ID
    name: str
    slug: Optional[str]
    is_active: bool
    paylink_enabled: bool

    @strawberry.field
    def branches(self) -> list["BranchType"]:
        # Uses prefetch cache when available.
        branches = getattr(self._obj, "_prefetched_objects_cache", {}).get("branches")
        if branches is None:
            branches = list(self._obj.branches.filter(is_active=True).select_related("organization").all())
        return _attach_list(list(branches))


@strawberry.type
class BranchType:
    id: strawberry.ID
    title: str
    slug: Optional[str]
    address: str
    is_active: bool
    paylink_enabled: bool
    paylink_amount: int

    @strawberry.field
    def organization(self) -> OrganizationType:
        org = self._obj.organization
        setattr(org, "_obj", org)
        return org

    @strawberry.field
    def specialists(self) -> list[SpecialistType]:
        # Uses prefetch cache when available.
        specialists = getattr(self._obj, "_prefetched_objects_cache", {}).get("specialists")
        if specialists is None:
            specialists = list(self._obj.specialists.filter(is_active=True).order_by("sort_order", "id").all())
        return _attach_list(list(specialists))


@strawberry.type
class ServiceType:
    id: strawberry.ID
    name: str
    price: int
    duration_min: int
    description: Optional[str]
    is_active: bool
    sort_order: int


@strawberry.type
class ProfessionalType:
    id: strawberry.ID
    full_name: str
    slug: Optional[str]
    rating: float
    rating_count: int
    experience_years: int
    bio: str
    education: str
    slot_duration_min: int
    consultation_type: str
    gender: str
    is_active: bool
    is_accepting_new: bool

    @strawberry.field
    def photo_url(self) -> str:
        from api.v1.utils import public_absolute_url

        raw = getattr(self._obj, "photo_url", None)
        if not raw:
            return ""
        if hasattr(raw, "url"):
            return public_absolute_url(raw.url)
        return public_absolute_url(str(raw))

    @strawberry.field
    def branches(self) -> list[BranchType]:
        branches = getattr(self._obj, "_prefetched_objects_cache", {}).get("branches")
        if branches is None:
            branches = list(self._obj.branches.filter(is_active=True).select_related("organization").all())
        return _attach_list(list(branches))

    @strawberry.field
    def services(self) -> list[ServiceType]:
        services = getattr(self._obj, "_prefetched_objects_cache", {}).get("services")
        if services is None:
            services = list(self._obj.services.filter(is_active=True).order_by("sort_order", "id").all())
        return _attach_list(list(services))

    @strawberry.field
    def specialties(self) -> list[str]:
        # Prefer prefetched specialties to avoid N+1.
        items = getattr(self._obj, "_prefetched_objects_cache", {}).get("professional_specialties")
        if items is None:
            items = list(
                self._obj.professional_specialties.select_related("specialist")
                .order_by("-is_primary", "specialist__sort_order")
                .all()
            )
        # Sort in python to keep deterministic output.
        items = sorted(
            items,
            key=lambda ps: (
                0 if getattr(ps, "is_primary", False) else 1,
                getattr(getattr(ps, "specialist", None), "sort_order", 0),
                getattr(getattr(ps, "specialist", None), "id", 0),
            ),
        )
        return [ps.specialist.title for ps in items if getattr(ps, "specialist", None)]


def _attach_obj(obj, gql_type):
    # Strawberry can map Django objects directly, but we want to attach original obj
    # for computed fields without re-fetching.
    setattr(obj, "_obj", obj)
    return obj


def _attach_list(items):
    # Attach `_obj` to each Django model instance.
    for it in items:
        setattr(it, "_obj", it)
    return items


def _time_to_str(t: Optional[time]) -> Optional[str]:
    if t is None:
        return None
    return t.strftime("%H:%M")


def _parse_time(value: Optional[str]) -> Optional[time]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        return timezone.datetime(2000, 1, 1, int(hh), int(mm)).time()
    except Exception:
        raise gql_error(
            error="validation_error",
            message="Невалидные данные",
            details={"time": ["Ожидается формат HH:MM"]},
        )


def _parse_date(value: str) -> date:
    try:
        return timezone.datetime.fromisoformat(value).date()
    except Exception:
        raise gql_error(
            error="validation_error",
            message="Невалидные данные",
            details={"date": ["Ожидается формат YYYY-MM-DD"]},
        )


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"

    @strawberry.field
    def specialists(self, info: Info, is_active: bool = True) -> list[SpecialistType]:
        qs = Specialist.objects.all().order_by("sort_order", "id")
        if is_active:
            qs = qs.filter(is_active=True)
        return _attach_list(list(qs))

    @strawberry.field
    def organizations(self, info: Info, is_active: bool = True) -> list[OrganizationType]:
        qs = (
            Organization.objects.all()
            .prefetch_related(
                Prefetch(
                    "branches",
                    queryset=Branch.objects.filter(is_active=True)
                    .select_related("organization")
                    .order_by("id"),
                )
            )
            .order_by("name", "id")
        )
        if is_active:
            qs = qs.filter(is_active=True)
        return _attach_list(list(qs))

    @strawberry.field
    def branches(
        self,
        info: Info,
        organization_id: Optional[int] = None,
        organization_slug: Optional[str] = None,
        is_active: bool = True,
    ) -> list[BranchType]:
        qs = (
            Branch.objects.select_related("organization")
            .prefetch_related(
                Prefetch(
                    "specialists",
                    queryset=Specialist.objects.filter(is_active=True).order_by("sort_order", "id"),
                )
            )
            .all()
            .order_by("id")
        )
        if is_active:
            qs = qs.filter(is_active=True)
        if organization_id is not None:
            qs = qs.filter(organization_id=organization_id)
        if organization_slug:
            qs = qs.filter(organization__slug=organization_slug)
        return _attach_list(list(qs))

    @strawberry.field
    def professionals(
        self,
        info: Info,
        specialist_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        search: Optional[str] = None,
        is_active: bool = True,
        is_accepting_new: bool = True,
    ) -> list[ProfessionalType]:
        qs = (
            Professional.objects.all()
            .prefetch_related(
                Prefetch(
                    "branches",
                    queryset=Branch.objects.filter(is_active=True)
                    .select_related("organization")
                    .order_by("id"),
                ),
                Prefetch(
                    "services",
                    queryset=Service.objects.filter(is_active=True).order_by("sort_order", "id"),
                ),
                Prefetch(
                    "professional_specialties",
                    queryset=ProfessionalSpecialty.objects.select_related("specialist").order_by(
                        "-is_primary",
                        "specialist__sort_order",
                        "id",
                    ),
                ),
            )
            .order_by("id")
        )
        if is_active:
            qs = qs.filter(is_active=True)
        if is_accepting_new:
            qs = qs.filter(is_accepting_new=True)
        if branch_id is not None:
            qs = qs.filter(branches__id=branch_id)
        if organization_id is not None:
            qs = qs.filter(branches__organization_id=organization_id)
        if specialist_id is not None:
            qs = qs.filter(professional_specialties__specialist_id=specialist_id)
        if search:
            qs = qs.filter(full_name__icontains=search)
        return _attach_list(list(qs.distinct()))

    @strawberry.field
    def professional_by_id(self, info: Info, id: strawberry.ID) -> Optional[ProfessionalType]:
        # Example of auth-aware field: allow fetching even public, but keep a place to enforce.
        _ = get_user_from_request(info.context.request)
        obj = (
            Professional.objects.prefetch_related(
                Prefetch(
                    "branches",
                    queryset=Branch.objects.filter(is_active=True)
                    .select_related("organization")
                    .order_by("id"),
                ),
                Prefetch(
                    "services",
                    queryset=Service.objects.filter(is_active=True).order_by("sort_order", "id"),
                ),
                Prefetch(
                    "professional_specialties",
                    queryset=ProfessionalSpecialty.objects.select_related("specialist").order_by(
                        "-is_primary",
                        "specialist__sort_order",
                        "id",
                    ),
                ),
            )
            .filter(id=id)
            .first()
        )
        if obj is not None:
            setattr(obj, "_obj", obj)
        return obj

    @strawberry.field
    def services(
        self,
        info: Info,
        professional_id: Optional[int] = None,
        is_active: bool = True,
    ) -> list[ServiceType]:
        qs = Service.objects.all().order_by("sort_order", "id")
        if is_active:
            qs = qs.filter(is_active=True)
        if professional_id is not None:
            qs = qs.filter(professionals__id=professional_id)
        return _attach_list(list(qs.distinct()))

    @strawberry.field
    def my_bookings(self, info: Info) -> list[BookingType]:
        """JWT-protected. Returns current client's bookings."""

        auth = get_user_from_request(info.context.request)
        user = auth.user
        if not getattr(user, "is_authenticated", False):
            raise gql_error(error="not_authenticated", message="Не авторизован")

        from apps.organizations.models import Booking  # local import to avoid cycles

        client = getattr(user, "client", None)
        if not client:
            return []

        qs = (
            Booking.objects.select_related("professional")
            .filter(client=client)
            .order_by("-created_at", "-id")
        )
        return _attach_list(list(qs))

    @strawberry.field
    def professional_calendar(
        self,
        info: Info,
        professional_id: int,
        days: int = 30,
        duration_min: Optional[int] = None,
        start_date: Optional[str] = None,
    ) -> JSON:
        """Public availability calendar (analogue of GET /api/v1/professionals/{id}/calendar).

        Returns JSON array items:
          {date,label,is_available,slots_count,times}
        """

        professional = Professional.objects.filter(id=int(professional_id), is_active=True).first()
        if not professional:
            raise gql_error(error="not_found", message="Специалист не найден")

        sd = _parse_date(start_date) if start_date else None
        return professional.get_calendar(days=int(days), duration_min=duration_min, start_date=sd)

    @strawberry.field
    def professional_available_times(
        self,
        info: Info,
        professional_id: int,
        date: str,
        duration_min: int,
    ) -> list[str]:
        """Public list of available start times (analogue of GET /available-times)."""

        professional = Professional.objects.filter(id=int(professional_id), is_active=True).first()
        if not professional:
            raise gql_error(error="not_found", message="Специалист не найден")
        d = _parse_date(date)
        return professional._get_free_slots_for_date(d, duration_min=int(duration_min))

    @strawberry.field
    def admin_bookings(
        self,
        info: Info,
        client_phone: Optional[str] = None,
        professional_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        date: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[BookingAdminType]:
        """Search bookings for bot/admin (simple filters)."""

        require_admin(info)

        from apps.organizations.models import Booking

        qs = Booking.objects.select_related("client", "professional", "branch")
        if client_phone:
            normalized = _normalize_and_validate_phone(client_phone)
            qs = qs.filter(client__phone=normalized)
        if professional_id is not None:
            qs = qs.filter(professional_id=int(professional_id))
        if branch_id is not None:
            qs = qs.filter(branch_id=int(branch_id))
        if date:
            qs = qs.filter(booking_date=_parse_date(date))
        if status:
            qs = qs.filter(status=status)
        qs = qs.order_by("-booking_date", "-booking_time", "-id")[: max(1, min(int(limit), 200))]
        return [BookingAdminType.from_obj(o) for o in qs]


@strawberry.type
class ProfessionalScheduleItem:
    day_of_week: int
    is_working: bool
    start_time: Optional[str]
    end_time: Optional[str]
    break_start: Optional[str]
    break_end: Optional[str]


@strawberry.input
class ProfessionalScheduleItemInput:
    day_of_week: int
    is_working: bool
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    break_start: Optional[str] = None
    break_end: Optional[str] = None


@strawberry.type
class ProfessionalScheduleExceptionType:
    id: strawberry.ID
    date: str
    is_day_off: bool
    reason: str
    start_time: Optional[str]
    end_time: Optional[str]
    break_start: Optional[str]
    break_end: Optional[str]


@strawberry.type
class BranchScheduleItem:
    day_of_week: int
    is_working: bool
    start_time: Optional[str]
    end_time: Optional[str]
    break_start: Optional[str]
    break_end: Optional[str]


def _schedule_item_from_obj(obj: ProfessionalSchedule) -> ProfessionalScheduleItem:
    return ProfessionalScheduleItem(
        day_of_week=int(obj.day_of_week),
        is_working=bool(obj.is_working),
        start_time=_time_to_str(obj.start_time),
        end_time=_time_to_str(obj.end_time),
        break_start=_time_to_str(obj.break_start),
        break_end=_time_to_str(obj.break_end),
    )


def _branch_schedule_item_from_obj(obj: BranchSchedule) -> BranchScheduleItem:
    return BranchScheduleItem(
        day_of_week=int(obj.day_of_week),
        is_working=bool(obj.is_working),
        start_time=_time_to_str(obj.start_time),
        end_time=_time_to_str(obj.end_time),
        break_start=_time_to_str(obj.break_start),
        break_end=_time_to_str(obj.break_end),
    )


def _exception_from_obj(obj: ScheduleException) -> ProfessionalScheduleExceptionType:
    return ProfessionalScheduleExceptionType(
        id=str(obj.id),
        date=obj.date.isoformat(),
        is_day_off=bool(obj.is_day_off),
        reason=obj.reason or "",
        start_time=_time_to_str(obj.start_time),
        end_time=_time_to_str(obj.end_time),
        break_start=_time_to_str(obj.break_start),
        break_end=_time_to_str(obj.break_end),
    )


@strawberry.type
class ApiResult:
    ok: bool
    error: Optional[str] = None
    message: Optional[str] = None
    details: Optional[JSON] = None


@strawberry.type
class PaylinkData:
    payment_intent_id: int
    transaction_id: str
    amount: int
    paylink_url: str


@strawberry.type
class CreatePaylinkResult(ApiResult):
    data: Optional[PaylinkData] = None


@strawberry.type
class BookingCreateData:
    id: int
    confirmation_code: str
    organization_id: Optional[int]
    branch_id: Optional[int]
    date: str
    time: str
    total_price: int
    status: str


@strawberry.type
class CreateBookingResult(ApiResult):
    data: Optional[BookingCreateData] = None


@strawberry.type
class CancelBookingResult(ApiResult):
    pass


def _validation_error(details: Any) -> ApiResult:
    return ApiResult(ok=False, error="validation_error", message="Невалидные данные", details=details)


@strawberry.type
class ErrorDemo:
    ok: bool


@strawberry.type
class Mutation:
    # -------------------- Admin/Bot mutations --------------------

    @strawberry.mutation
    def admin_create_specialist(
        self,
        info: Info,
        title: str,
        slug: Optional[str] = None,
        description: str = "",
        sort_order: int = 0,
        is_active: bool = True,
    ) -> SpecialistType:
        require_admin(info)

        title = (title or "").strip()
        if not title:
            raise gql_error(error="validation_error", message="Невалидные данные", details={"title": ["Обязательное поле"]})

        slug_value = (slug or "").strip() or _make_unique_slug(model=Specialist, base=title)
        obj = Specialist.objects.create(
            title=title,
            slug=slug_value,
            description=description or "",
            sort_order=int(sort_order or 0),
            is_active=bool(is_active),
        )
        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_update_specialist(
        self,
        info: Info,
        id: int,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> SpecialistType:
        require_admin(info)

        obj = Specialist.objects.filter(id=int(id)).first()
        if not obj:
            raise gql_error(error="not_found", message="Специализация не найдена")

        if title is not None:
            obj.title = (title or "").strip()
        if slug is not None:
            obj.slug = (slug or "").strip() or obj.slug
        if description is not None:
            obj.description = description or ""
        if sort_order is not None:
            obj.sort_order = int(sort_order)
        if is_active is not None:
            obj.is_active = bool(is_active)

        if not obj.slug and obj.title:
            obj.slug = _make_unique_slug(model=Specialist, base=obj.title)
        obj.save()

        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_create_professional(
        self,
        info: Info,
        full_name: str,
        slug: Optional[str] = None,
        bio: str = "",
        education: str = "",
        experience_years: int = 0,
        slot_duration_min: int = 30,
        consultation_type: str = "offline",
        gender: str = "female",
        is_active: bool = True,
        is_accepting_new: bool = True,
        branch_ids: Optional[list[int]] = None,
        primary_specialist_id: Optional[int] = None,
    ) -> ProfessionalType:
        require_admin(info)

        name = (full_name or "").strip()
        if not name:
            raise gql_error(error="validation_error", message="Невалидные данные", details={"full_name": ["Обязательное поле"]})

        obj = Professional.objects.create(
            full_name=name,
            slug=(slug or "").strip() or None,
            bio=bio or "",
            education=education or "",
            experience_years=int(experience_years or 0),
            slot_duration_min=int(slot_duration_min or 30),
            consultation_type=consultation_type or "offline",
            gender=gender or "female",
            is_active=bool(is_active),
            is_accepting_new=bool(is_accepting_new),
            primary_specialist_id=int(primary_specialist_id) if primary_specialist_id else None,
        )
        if not obj.slug:
            obj.slug = _make_unique_slug(model=Professional, base=obj.full_name)
            obj.save(update_fields=["slug"])

        if branch_ids:
            branches = list(Branch.objects.filter(id__in=[int(x) for x in branch_ids]))
            obj.branches.set(branches)

        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_update_professional(
        self,
        info: Info,
        id: int,
        full_name: Optional[str] = None,
        slug: Optional[str] = None,
        bio: Optional[str] = None,
        education: Optional[str] = None,
        experience_years: Optional[int] = None,
        slot_duration_min: Optional[int] = None,
        consultation_type: Optional[str] = None,
        gender: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_accepting_new: Optional[bool] = None,
        branch_ids: Optional[list[int]] = None,
        primary_specialist_id: Optional[int] = None,
    ) -> ProfessionalType:
        require_admin(info)

        obj = Professional.objects.filter(id=int(id)).first()
        if not obj:
            raise gql_error(error="not_found", message="Специалист не найден")

        if full_name is not None:
            obj.full_name = (full_name or "").strip()
        if slug is not None:
            obj.slug = (slug or "").strip() or obj.slug
        if bio is not None:
            obj.bio = bio or ""
        if education is not None:
            obj.education = education or ""
        if experience_years is not None:
            obj.experience_years = int(experience_years)
        if slot_duration_min is not None:
            obj.slot_duration_min = int(slot_duration_min)
        if consultation_type is not None:
            obj.consultation_type = consultation_type or obj.consultation_type
        if gender is not None:
            obj.gender = gender or obj.gender
        if is_active is not None:
            obj.is_active = bool(is_active)
        if is_accepting_new is not None:
            obj.is_accepting_new = bool(is_accepting_new)
        if primary_specialist_id is not None:
            obj.primary_specialist_id = int(primary_specialist_id) if primary_specialist_id else None

        if not obj.slug and obj.full_name:
            obj.slug = _make_unique_slug(model=Professional, base=obj.full_name)

        obj.save()

        if branch_ids is not None:
            branches = list(Branch.objects.filter(id__in=[int(x) for x in branch_ids]))
            obj.branches.set(branches)

        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_set_professional_specialties(
        self,
        info: Info,
        professional_id: int,
        specialist_ids: list[int],
        primary_specialist_id: Optional[int] = None,
    ) -> ProfessionalType:
        require_admin(info)

        prof = Professional.objects.filter(id=int(professional_id)).first()
        if not prof:
            raise gql_error(error="not_found", message="Специалист не найден")

        specialist_ids_int = [int(x) for x in specialist_ids]
        specialists = list(Specialist.objects.filter(id__in=specialist_ids_int))
        if len(specialists) != len(set(specialist_ids_int)):
            raise gql_error(error="validation_error", message="Невалидные данные", details={"specialist_ids": ["Некоторые специализации не найдены"]})

        # Reset relations
        ProfessionalSpecialty.objects.filter(professional=prof).delete()
        primary_id = int(primary_specialist_id) if primary_specialist_id else None
        for sid in specialist_ids_int:
            ProfessionalSpecialty.objects.create(
                professional=prof,
                specialist_id=sid,
                is_primary=bool(primary_id and sid == primary_id),
            )

        if primary_id:
            prof.primary_specialist_id = primary_id
            prof.save(update_fields=["primary_specialist", "updated_at"])

        setattr(prof, "_obj", prof)
        return prof

    @strawberry.mutation
    def admin_set_professional_services(
        self,
        info: Info,
        professional_id: int,
        service_ids: list[int],
    ) -> ProfessionalType:
        require_admin(info)

        prof = Professional.objects.filter(id=int(professional_id)).first()
        if not prof:
            raise gql_error(error="not_found", message="Специалист не найден")

        service_ids_int = [int(x) for x in service_ids]
        services = list(Service.objects.filter(id__in=service_ids_int))
        if len(services) != len(set(service_ids_int)):
            raise gql_error(error="validation_error", message="Невалидные данные", details={"service_ids": ["Некоторые услуги не найдены"]})

        # Soft attach via through table.
        ProfessionalService.objects.filter(professional=prof).delete()
        for sid in service_ids_int:
            ProfessionalService.objects.create(professional=prof, service_id=sid, is_active=True)

        setattr(prof, "_obj", prof)
        return prof

    @strawberry.mutation
    def admin_set_professional_week_schedule(
        self,
        info: Info,
        professional_id: int,
        items: list[ProfessionalScheduleItemInput],
    ) -> ApiResult:
        """Replace weekly schedule (analogue of PRO schedule update)."""

        require_admin(info)

        prof = Professional.objects.filter(id=int(professional_id)).first()
        if not prof:
            raise gql_error(error="not_found", message="Специалист не найден")

        # Replace schedule completely.
        ProfessionalSchedule.objects.filter(professional=prof).delete()
        for it in items:
            ProfessionalSchedule.objects.create(
                professional=prof,
                day_of_week=int(it.day_of_week),
                is_working=bool(it.is_working),
                start_time=_parse_time(it.start_time),
                end_time=_parse_time(it.end_time),
                break_start=_parse_time(it.break_start),
                break_end=_parse_time(it.break_end),
            )

        return ApiResult(ok=True, message="График обновлён")

    @strawberry.mutation
    def admin_add_professional_exception(
        self,
        info: Info,
        professional_id: int,
        date: str,
        is_day_off: bool = True,
        reason: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        break_start: Optional[str] = None,
        break_end: Optional[str] = None,
    ) -> ProfessionalScheduleExceptionType:
        require_admin(info)

        prof = Professional.objects.filter(id=int(professional_id)).first()
        if not prof:
            raise gql_error(error="not_found", message="Специалист не найден")

        obj = ScheduleException.objects.create(
            professional=prof,
            date=_parse_date(date),
            is_day_off=bool(is_day_off),
            reason=reason or "",
            start_time=_parse_time(start_time),
            end_time=_parse_time(end_time),
            break_start=_parse_time(break_start),
            break_end=_parse_time(break_end),
        )
        return _exception_from_obj(obj)

    @strawberry.mutation
    def admin_delete_professional_exception(self, info: Info, exception_id: int) -> ApiResult:
        require_admin(info)

        deleted, _ = ScheduleException.objects.filter(id=int(exception_id)).delete()
        if not deleted:
            raise gql_error(error="not_found", message="Исключение не найдено")
        return ApiResult(ok=True, message="Удалено")

    @strawberry.mutation
    def admin_create_organization(
        self,
        info: Info,
        name: str,
        slug: Optional[str] = None,
        is_active: bool = True,
        paylink_enabled: bool = True,
    ) -> OrganizationType:
        require_admin(info)

        name = (name or "").strip()
        if not name:
            raise gql_error(
                error="validation_error",
                message="Невалидные данные",
                details={"name": ["Обязательное поле"]},
            )

        obj = Organization.objects.create(
            name=name,
            slug=(slug or "").strip() or None,
            is_active=bool(is_active),
            paylink_enabled=bool(paylink_enabled),
        )
        if not obj.slug:
            obj.slug = _make_unique_slug(model=Organization, base=obj.name)
            obj.save(update_fields=["slug"])
        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_update_organization(
        self,
        info: Info,
        id: int,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        is_active: Optional[bool] = None,
        paylink_enabled: Optional[bool] = None,
    ) -> OrganizationType:
        require_admin(info)

        obj = Organization.objects.filter(id=int(id)).first()
        if not obj:
            raise gql_error(error="not_found", message="Организация не найдена")

        if name is not None:
            obj.name = (name or "").strip()
        if slug is not None:
            obj.slug = (slug or "").strip() or obj.slug
        if is_active is not None:
            obj.is_active = bool(is_active)
        if paylink_enabled is not None:
            obj.paylink_enabled = bool(paylink_enabled)

        if not obj.slug and obj.name:
            obj.slug = _make_unique_slug(model=Organization, base=obj.name)

        obj.save()
        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_create_branch(
        self,
        info: Info,
        organization_id: int,
        title: str = "",
        address: str = "",
        slug: Optional[str] = None,
        is_active: bool = True,
        paylink_enabled: bool = False,
        paylink_amount: int = 0,
        paylink_token: str = "",
        specialist_ids: Optional[list[int]] = None,
    ) -> BranchType:
        require_admin(info)

        org = Organization.objects.filter(id=int(organization_id)).first()
        if not org:
            raise gql_error(
                error="validation_error",
                message="Невалидные данные",
                details={"organization_id": ["Организация не найдена"]},
            )

        obj = Branch.objects.create(
            organization=org,
            title=title or "",
            address=address or "",
            slug=(slug or "").strip() or None,
            is_active=bool(is_active),
            paylink_enabled=bool(paylink_enabled),
            paylink_amount=int(paylink_amount or 0),
            paylink_token=paylink_token or "",
        )
        if specialist_ids:
            specs = list(Specialist.objects.filter(id__in=[int(x) for x in specialist_ids]))
            obj.specialists.set(specs)

        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_update_branch(
        self,
        info: Info,
        id: int,
        title: Optional[str] = None,
        address: Optional[str] = None,
        slug: Optional[str] = None,
        is_active: Optional[bool] = None,
        paylink_enabled: Optional[bool] = None,
        paylink_amount: Optional[int] = None,
        paylink_token: Optional[str] = None,
        specialist_ids: Optional[list[int]] = None,
    ) -> BranchType:
        require_admin(info)

        obj = Branch.objects.filter(id=int(id)).first()
        if not obj:
            raise gql_error(error="not_found", message="Филиал не найден")

        if title is not None:
            obj.title = title or ""
        if address is not None:
            obj.address = address or ""
        if slug is not None:
            obj.slug = (slug or "").strip() or obj.slug
        if is_active is not None:
            obj.is_active = bool(is_active)
        if paylink_enabled is not None:
            obj.paylink_enabled = bool(paylink_enabled)
        if paylink_amount is not None:
            obj.paylink_amount = int(paylink_amount)
        if paylink_token is not None:
            obj.paylink_token = paylink_token or ""

        obj.save()

        if specialist_ids is not None:
            specs = list(Specialist.objects.filter(id__in=[int(x) for x in specialist_ids]))
            obj.specialists.set(specs)

        setattr(obj, "_obj", obj)
        return obj

    @strawberry.mutation
    def admin_set_branch_week_schedule(
        self,
        info: Info,
        branch_id: int,
        items: list[ProfessionalScheduleItemInput],
    ) -> ApiResult:
        """Replace weekly schedule for a branch."""

        require_admin(info)

        br = Branch.objects.filter(id=int(branch_id)).first()
        if not br:
            raise gql_error(error="not_found", message="Филиал не найден")

        BranchSchedule.objects.filter(branch=br).delete()
        for it in items:
            BranchSchedule.objects.create(
                branch=br,
                day_of_week=int(it.day_of_week),
                is_working=bool(it.is_working),
                start_time=_parse_time(it.start_time),
                end_time=_parse_time(it.end_time),
                break_start=_parse_time(it.break_start),
                break_end=_parse_time(it.break_end),
            )

        return ApiResult(ok=True, message="График филиала обновлён")

    @strawberry.mutation
    def admin_create_service(
        self,
        info: Info,
        name: str,
        price: int,
        duration_min: int = 30,
        description: str = "",
        sort_order: int = 0,
        is_active: bool = True,
        professional_ids: Optional[list[int]] = None,
    ) -> ServiceType:
        require_admin(info)

        name = (name or "").strip()
        if not name:
            raise gql_error(error="validation_error", message="Невалидные данные", details={"name": ["Обязательное поле"]})
        if int(price) < 0:
            raise gql_error(error="validation_error", message="Невалидные данные", details={"price": ["Цена не может быть отрицательной"]})

        svc = Service.objects.create(
            name=name,
            price=int(price),
            duration_min=int(duration_min or 30),
            description=description or "",
            sort_order=int(sort_order or 0),
            is_active=bool(is_active),
        )
        if professional_ids:
            pros = list(Professional.objects.filter(id__in=[int(x) for x in professional_ids]))
            svc.professionals.set(pros)

        setattr(svc, "_obj", svc)
        return svc

    @strawberry.mutation
    def admin_update_service(
        self,
        info: Info,
        id: int,
        name: Optional[str] = None,
        price: Optional[int] = None,
        duration_min: Optional[int] = None,
        description: Optional[str] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
        professional_ids: Optional[list[int]] = None,
    ) -> ServiceType:
        require_admin(info)

        svc = Service.objects.filter(id=int(id)).first()
        if not svc:
            raise gql_error(error="not_found", message="Услуга не найдена")

        if name is not None:
            svc.name = (name or "").strip()
        if price is not None:
            svc.price = int(price)
        if duration_min is not None:
            svc.duration_min = int(duration_min)
        if description is not None:
            svc.description = description
        if sort_order is not None:
            svc.sort_order = int(sort_order)
        if is_active is not None:
            svc.is_active = bool(is_active)
        svc.save()

        if professional_ids is not None:
            pros = list(Professional.objects.filter(id__in=[int(x) for x in professional_ids]))
            svc.professionals.set(pros)

        setattr(svc, "_obj", svc)
        return svc

    # -------------------- Admin/Bot bookings --------------------

    @strawberry.mutation
    def admin_create_booking_for_client(
        self,
        info: Info,
        client_phone: str,
        client_full_name: str,
        professional_id: int,
        date: str,
        time: str,
        service_ids: list[int],
        branch_id: Optional[int] = None,
        payment_intent_id: Optional[int] = None,
        allow_incomplete_profile: bool = True,
        skip_payment_requirement: bool = False,
    ) -> CreateBookingResult:
        """Create booking on behalf of a client (bot/admin).

        Auth: X-BOT-TOKEN / staff.
        """

        require_admin(info)

        from django.db import transaction

        from apps.organizations.models import Booking, PaymentIntent

        from api.v1.utils import bishek_now, make_confirmation_code
        from api.v1.views import _is_paylink_enabled_for_branch

        client = _get_or_create_client_by_phone(phone=client_phone, full_name=client_full_name)
        if not allow_incomplete_profile and not client.is_profile_completed:
            raise gql_error(
                error="profile_incomplete",
                message="Профиль не заполнен",
                details={"required": ["phone"]},
            )

        professional = Professional.objects.filter(id=int(professional_id), is_active=True).first()
        if not professional:
            raise gql_error(error="not_found", message="Специалист не найден")

        booking_date = _parse_date(date)
        booking_time = _parse_hhmm_to_time(time)

        with transaction.atomic():
            # resolve branch
            branch = None
            if branch_id is not None:
                branch = (
                    Branch.objects.select_related("organization")
                    .filter(id=int(branch_id), is_active=True, organization__is_active=True)
                    .first()
                )
                if not branch:
                    raise gql_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"branch_id": ["Филиал не найден"]},
                    )
            if branch is None:
                branch = (
                    professional.branches.select_related("organization")
                    .filter(is_active=True, organization__is_active=True)
                    .first()
                )

            # enforce payment when needed (can be skipped for call-center/bot scenarios)
            payment_intent = None
            requires_payment = bool(
                branch
                and _is_paylink_enabled_for_branch(branch=branch)
                and int(getattr(branch, "paylink_amount", 0) or 0) > 0
            )
            if requires_payment:
                if payment_intent_id:
                    payment_intent = PaymentIntent.objects.select_related("branch").filter(id=int(payment_intent_id)).first()
                    if not payment_intent:
                        raise gql_error(
                            error="validation_error",
                            message="Невалидные данные",
                            details={"payment_intent_id": ["Платёж не найден"]},
                        )
                    if payment_intent.status != PaymentIntent.STATUS_PAID:
                        raise gql_error(
                            error="payment_not_paid",
                            message="Платёж не подтверждён",
                            details={"payment_intent_id": payment_intent.id, "status": payment_intent.status},
                        )
                    if branch and payment_intent.branch_id != branch.id:
                        raise gql_error(
                            error="validation_error",
                            message="Невалидные данные",
                            details={"payment_intent_id": ["Платёж относится к другому филиалу"]},
                        )
                elif not skip_payment_requirement:
                    raise gql_error(
                        error="payment_required",
                        message="Требуется оплата брони",
                        details={"branch_id": branch.id, "amount": int(branch.paylink_amount)},
                    )

            services = _resolve_services_for_professional(professional=professional, service_ids=service_ids)

            now = bishek_now()
            if booking_date < now.date() or (booking_date == now.date() and booking_time <= now.time()):
                raise gql_error(error="date_in_past", message="Дата записи уже прошла")

            total_price = sum(svc.price for svc in services)
            total_duration_min = sum(svc.duration_min for svc in services)
            _ensure_slot_available(
                professional=professional,
                booking_date=booking_date,
                booking_time=booking_time,
                total_duration_min=total_duration_min,
            )

            confirmation_code = make_confirmation_code()
            for _ in range(10):
                if not Booking.objects.filter(confirmation_code=confirmation_code).exists():
                    break
                confirmation_code = make_confirmation_code()

            booking = Booking.objects.create(
                client=client,
                professional=professional,
                branch=branch,
                payment_intent=payment_intent,
                booking_date=booking_date,
                booking_time=booking_time,
                status="confirmed",
                confirmation_code=confirmation_code,
                total_price=total_price,
                total_duration_min=total_duration_min,
            )
            booking.set_services(services)

        return CreateBookingResult(
            ok=True,
            data=BookingCreateData(
                id=booking.id,
                confirmation_code=booking.confirmation_code,
                organization_id=branch.organization_id if branch else None,
                branch_id=branch.id if branch else None,
                date=booking.booking_date.isoformat(),
                time=booking.booking_time.strftime("%H:%M"),
                total_price=total_price,
                status=booking.status,
            ),
        )

    @strawberry.mutation
    def admin_cancel_booking(
        self,
        info: Info,
        booking_id: int,
        reason: str = "",
        cancelled_by: str = "bot",
    ) -> ApiResult:
        """Cancel any booking by id (bot/admin)."""

        require_admin(info)

        from apps.organizations.models import Booking

        booking = Booking.objects.filter(id=int(booking_id)).first()
        if not booking:
            raise gql_error(error="not_found", message="Запись не найдена")

        booking.status = "cancelled"
        booking.cancelled_by = (cancelled_by or "bot")[:20]
        booking.cancellation_reason = (reason or "")[:255]
        booking.save(update_fields=["status", "cancelled_by", "cancellation_reason", "updated_at"])
        return ApiResult(ok=True, message="Запись отменена")

    @strawberry.mutation
    def admin_reschedule_booking(
        self,
        info: Info,
        booking_id: int,
        date: str,
        time: str,
        professional_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        service_ids: Optional[list[int]] = None,
        payment_intent_id: Optional[int] = None,
        skip_payment_requirement: bool = False,
    ) -> ApiResult:
        """Move booking to another date/time (and optionally change professional/branch/services)."""

        require_admin(info)

        from django.db import transaction

        from api.v1.views import _is_paylink_enabled_for_branch

        from apps.organizations.models import Booking

        booking = Booking.objects.select_related("professional", "branch", "payment_intent").filter(id=int(booking_id)).first()
        if not booking:
            raise gql_error(error="not_found", message="Запись не найдена")
        if booking.status == "cancelled":
            raise gql_error(error="validation_error", message="Невалидные данные", details={"booking_id": ["Запись уже отменена"]})

        new_prof = booking.professional
        if professional_id is not None:
            new_prof = Professional.objects.filter(id=int(professional_id), is_active=True).first()
            if not new_prof:
                raise gql_error(error="validation_error", message="Невалидные данные", details={"professional_id": ["Специалист не найден"]})

        new_branch = booking.branch
        if branch_id is not None:
            new_branch = (
                Branch.objects.select_related("organization")
                .filter(id=int(branch_id), is_active=True, organization__is_active=True)
                .first()
            )
            if not new_branch:
                raise gql_error(error="validation_error", message="Невалидные данные", details={"branch_id": ["Филиал не найден"]})

        new_date = _parse_date(date)
        new_time = _parse_hhmm_to_time(time)

        with transaction.atomic():
            # update services if requested
            if service_ids is not None:
                services = _resolve_services_for_professional(professional=new_prof, service_ids=service_ids)
                booking.total_price = sum(s.price for s in services)
                booking.total_duration_min = sum(s.duration_min for s in services)
                booking.set_services(services)

            # availability check (exclude current booking)
            _ensure_slot_available(
                professional=new_prof,
                booking_date=new_date,
                booking_time=new_time,
                total_duration_min=int(booking.total_duration_min or 30),
                exclude_booking_id=int(booking.id),
            )

            # enforce payment if branch requires it (unless explicitly skipped)
            from apps.organizations.models import PaymentIntent

            requires_payment = bool(
                new_branch
                and _is_paylink_enabled_for_branch(branch=new_branch)
                and int(getattr(new_branch, "paylink_amount", 0) or 0) > 0
            )
            if requires_payment:
                resolved_intent = None
                if payment_intent_id:
                    resolved_intent = PaymentIntent.objects.select_related("branch").filter(id=int(payment_intent_id)).first()
                    if not resolved_intent:
                        raise gql_error(
                            error="validation_error",
                            message="Невалидные данные",
                            details={"payment_intent_id": ["Платёж не найден"]},
                        )
                    if resolved_intent.status != PaymentIntent.STATUS_PAID:
                        raise gql_error(
                            error="payment_not_paid",
                            message="Платёж не подтверждён",
                            details={"payment_intent_id": resolved_intent.id, "status": resolved_intent.status},
                        )
                    if resolved_intent.branch_id != new_branch.id:
                        raise gql_error(
                            error="validation_error",
                            message="Невалидные данные",
                            details={"payment_intent_id": ["Платёж относится к другому филиалу"]},
                        )
                elif booking.payment_intent_id:
                    # keep existing paid intent only if it matches the new branch
                    if booking.payment_intent and booking.payment_intent.status == PaymentIntent.STATUS_PAID and booking.payment_intent.branch_id == new_branch.id:
                        resolved_intent = booking.payment_intent
                elif not skip_payment_requirement:
                    raise gql_error(
                        error="payment_required",
                        message="Требуется оплата брони",
                        details={"branch_id": new_branch.id, "amount": int(new_branch.paylink_amount)},
                    )
                booking.payment_intent = resolved_intent
            else:
                # if moved to non-paylink branch we can detach intent
                booking.payment_intent = None

            booking.professional = new_prof
            booking.branch = new_branch
            booking.booking_date = new_date
            booking.booking_time = new_time
            booking.save(update_fields=["professional", "branch", "booking_date", "booking_time", "payment_intent", "total_price", "total_duration_min", "updated_at"])

        return ApiResult(ok=True, message="Запись перенесена")

    @strawberry.mutation
    def create_paylink(self, info: Info, branch_id: int) -> CreatePaylinkResult:
        """GraphQL analogue of POST /api/v1/payments/paylink."""

        # Optional auth: if user is authenticated, intent will be linked to client.
        from django.conf import settings
        from django.db import transaction

        import requests

        from apps.organizations.models import Client, PaymentIntent

        from api.v1.views import _is_paylink_enabled_for_branch

        try:
            branch = Branch.objects.select_related("organization").get(
                id=int(branch_id),
                is_active=True,
                organization__is_active=True,
            )
        except Branch.DoesNotExist:
            return CreatePaylinkResult(ok=False, error="not_found", message="Филиал не найден")

        if not _is_paylink_enabled_for_branch(branch=branch):
            return CreatePaylinkResult(
                ok=False,
                error="validation_error",
                message="Невалидные данные",
                details={"branch_id": ["Для этого филиала оплата/бронь отключена"]},
            )

        amount = int(getattr(branch, "paylink_amount", 0) or 0)
        if amount <= 0:
            return CreatePaylinkResult(
                ok=False,
                error="validation_error",
                message="Невалидные данные",
                details={"amount": ["Сумма брони не задана"]},
            )

        branch_token = (getattr(branch, "paylink_token", "") or "").strip()
        global_token = (getattr(settings, "BAKAI_PAYLINK_TOKEN", "") or "").strip()
        bad_prefixes = ("TEST_", "PLACEHOLDER", "DUMMY")
        if branch_token and branch_token.upper().startswith(bad_prefixes):
            branch_token = ""
        token = branch_token or global_token
        if not token:
            return CreatePaylinkResult(ok=False, error="server_error", message="PayLink token не настроен")

        redirect_url = (getattr(settings, "PAYLINK_REDIRECT_URL", "") or "").strip()

        auth = get_user_from_request(info.context.request)
        client = None
        if getattr(auth.user, "is_authenticated", False):
            client = Client.objects.filter(user=auth.user).first()

        with transaction.atomic():
            intent = PaymentIntent.objects.create(
                branch=branch,
                client=client,
                amount=amount,
                comment="",
                status=PaymentIntent.STATUS_PENDING,
            )
            intent.comment = f"Оплата брони филиала #{branch.id} tx={intent.transaction_id}"
            intent.save(update_fields=["comment", "updated_at"])

        if redirect_url:
            sep = "&" if "?" in redirect_url else "?"
            redirect_url = f"{redirect_url}{sep}tx={intent.transaction_id}"

        base_url = (getattr(settings, "BAKAI_PAYLINK_BASE_URL", "https://openbanking-api.bakai.kg") or "").rstrip("/")
        url = f"{base_url}/api/PayLink/CreatePayLink"
        payload = {
            "amount": amount,
            "transactionID": str(intent.transaction_id),
            "comment": intent.comment,
            "redirectURL": redirect_url,
            "ttlUnits": 0,
            "ttl": 0,
        }

        if bool(getattr(settings, "PAYLINK_MOCK_ENABLED", False)):
            paylink_url = f"https://paylink.mock/{intent.transaction_id}"
            intent.paylink_url = paylink_url
            intent.provider_payload = {"request": payload, "response": paylink_url, "mock": True}
            intent.save(update_fields=["paylink_url", "provider_payload", "updated_at"])
            return CreatePaylinkResult(
                ok=True,
                data=PaylinkData(
                    payment_intent_id=intent.id,
                    transaction_id=str(intent.transaction_id),
                    amount=amount,
                    paylink_url=paylink_url,
                ),
            )

        try:
            r = requests.post(
                url,
                headers={
                    "accept": "*/*",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            r.raise_for_status()
            paylink_url = (r.text or "").strip().strip('"')
        except Exception as e:
            error_payload: dict[str, Any] = {"error": str(e)}
            try:
                error_payload["status_code"] = r.status_code  # type: ignore[name-defined]
                error_payload["response_text"] = (r.text or "").strip()  # type: ignore[name-defined]
            except Exception:
                pass
            intent.status = PaymentIntent.STATUS_FAILED
            intent.provider_payload = error_payload
            intent.save(update_fields=["status", "provider_payload", "updated_at"])
            return CreatePaylinkResult(
                ok=False,
                error="server_error",
                message="Не удалось создать PayLink",
                details=error_payload,
            )

        intent.paylink_url = paylink_url
        intent.provider_payload = {"request": payload, "response": paylink_url}
        intent.save(update_fields=["paylink_url", "provider_payload", "updated_at"])

        return CreatePaylinkResult(
            ok=True,
            data=PaylinkData(
                payment_intent_id=intent.id,
                transaction_id=str(intent.transaction_id),
                amount=amount,
                paylink_url=paylink_url,
            ),
        )

    @strawberry.mutation
    def create_booking(
        self,
        info: Info,
        professional_id: int,
        date: date,
        time: str,
        service_ids: list[int],
        branch_id: Optional[int] = None,
        payment_intent_id: Optional[int] = None,
    ) -> CreateBookingResult:
        """GraphQL analogue of POST /api/v1/bookings."""

        from datetime import timedelta

        from django.db import transaction
        from django.utils import timezone

        from apps.organizations.models import Booking, Client, PaymentIntent

        from api.v1.utils import bishek_now, make_confirmation_code
        from api.v1.views import _is_paylink_enabled_for_branch

        auth = get_user_from_request(info.context.request)
        if not getattr(auth.user, "is_authenticated", False):
            raise gql_error(error="not_authenticated", message="Не авторизован")

        client = Client.objects.filter(user=auth.user).first()
        if not client:
            raise gql_error(error="client_not_found", message="Клиент не найден")
        if not client.is_profile_completed:
            raise gql_error(
                error="profile_incomplete",
                message="Профиль не заполнен",
                details={"required": ["phone"]},
            )

        professional = Professional.objects.filter(id=int(professional_id), is_active=True).first()
        if not professional:
            raise gql_error(error="not_found", message="Специалист не найден")

        with transaction.atomic():
            branch = None
            if branch_id is not None:
                branch = (
                    Branch.objects.select_related("organization")
                    .filter(id=int(branch_id), is_active=True, organization__is_active=True)
                    .first()
                )
                if not branch:
                    raise gql_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"branch_id": ["Филиал не найден"]},
                    )

            if branch is None:
                branch = (
                    professional.branches.select_related("organization")
                    .filter(is_active=True, organization__is_active=True)
                    .first()
                )

            payment_intent = None
            if branch and _is_paylink_enabled_for_branch(branch=branch) and int(getattr(branch, "paylink_amount", 0) or 0) > 0:
                if not payment_intent_id:
                    raise gql_error(
                        error="payment_required",
                        message="Требуется оплата брони",
                        details={"branch_id": branch.id, "amount": int(branch.paylink_amount)},
                    )
                payment_intent = PaymentIntent.objects.select_related("branch").filter(id=int(payment_intent_id)).first()
                if not payment_intent:
                    raise gql_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"payment_intent_id": ["Платёж не найден"]},
                    )
                if payment_intent.status != PaymentIntent.STATUS_PAID:
                    raise gql_error(
                        error="payment_not_paid",
                        message="Платёж не подтверждён",
                        details={"payment_intent_id": payment_intent.id, "status": payment_intent.status},
                    )
                if branch and payment_intent.branch_id != branch.id:
                    raise gql_error(
                        error="validation_error",
                        message="Невалидные данные",
                        details={"payment_intent_id": ["Платёж относится к другому филиалу"]},
                    )

            # Parse time HH:MM
            try:
                hh, mm = time.split(":")
                booking_time = timezone.datetime(2000, 1, 1, int(hh), int(mm)).time()
            except Exception:
                raise gql_error(
                    error="validation_error",
                    message="Невалидные данные",
                    details={"time": ["Ожидается формат HH:MM"]},
                )

            # Services resolution must match REST (new M2M + legacy Service.professional).
            services = _resolve_services_for_professional(professional=professional, service_ids=service_ids)

            now = bishek_now()
            if date < now.date() or (date == now.date() and booking_time <= now.time()):
                raise gql_error(error="date_in_past", message="Дата записи уже прошла")

            free_slots = professional._get_free_slots_for_date(date)
            if booking_time.strftime("%H:%M") not in free_slots:
                raise gql_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                )

            total_price = sum(svc.price for svc in services)
            total_duration_min = sum(svc.duration_min for svc in services)

            slot_minutes = professional.slot_duration_min or 30
            slots_needed = max(1, total_duration_min // slot_minutes + (1 if total_duration_min % slot_minutes else 0))
            start_dt = timezone.datetime.combine(date, booking_time)
            slot_times = [(start_dt + timedelta(minutes=slot_minutes * i)).time() for i in range(slots_needed)]
            slot_strings = [t.strftime("%H:%M") for t in slot_times]
            if any(t not in free_slots for t in slot_strings):
                raise gql_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                )

            existing = (
                Booking.objects.filter(professional=professional, booking_date=date)
                .exclude(status="cancelled")
                .order_by("id")
            )
            booked = set(existing.values_list("booking_time", flat=True))
            for b in existing:
                if b.total_duration_min:
                    b_slots = max(1, b.total_duration_min // slot_minutes + (1 if b.total_duration_min % slot_minutes else 0))
                    b_start = timezone.datetime.combine(b.booking_date, b.booking_time)
                    for i in range(b_slots):
                        booked.add((b_start + timedelta(minutes=slot_minutes * i)).time())
            if any(t in booked for t in slot_times):
                raise gql_error(
                    error="slot_unavailable",
                    message="Выбранное время уже занято. Пожалуйста, выберите другое время.",
                )

            confirmation_code = make_confirmation_code()
            for _ in range(10):
                if not Booking.objects.filter(confirmation_code=confirmation_code).exists():
                    break
                confirmation_code = make_confirmation_code()

            booking = Booking.objects.create(
                client=client,
                professional=professional,
                branch=branch,
                payment_intent=payment_intent,
                booking_date=date,
                booking_time=booking_time,
                status="confirmed",
                confirmation_code=confirmation_code,
                total_price=total_price,
                total_duration_min=total_duration_min,
            )
            booking.set_services(services)

        return CreateBookingResult(
            ok=True,
            data=BookingCreateData(
                id=booking.id,
                confirmation_code=booking.confirmation_code,
                organization_id=branch.organization_id if branch else None,
                branch_id=branch.id if branch else None,
                date=booking.booking_date.isoformat(),
                time=booking.booking_time.strftime("%H:%M"),
                total_price=total_price,
                status=booking.status,
            ),
        )

    @strawberry.mutation
    def cancel_booking(self, info: Info, booking_id: int) -> CancelBookingResult:
        """GraphQL analogue of DELETE /api/v1/bookings/{booking_id}."""

        from datetime import timedelta

        from django.utils import timezone

        from apps.organizations.models import Booking, Client

        from api.v1.utils import bishek_now

        auth = get_user_from_request(info.context.request)
        if not getattr(auth.user, "is_authenticated", False):
            raise gql_error(error="not_authenticated", message="Не авторизован")

        client = Client.objects.filter(user=auth.user).first()
        if not client:
            raise gql_error(error="client_not_found", message="Клиент не найден")

        booking = Booking.objects.filter(id=int(booking_id), client=client).first()
        if not booking:
            raise gql_error(error="not_found", message="Запись не найдена")

        appt_dt = timezone.make_aware(timezone.datetime.combine(booking.booking_date, booking.booking_time))
        if appt_dt - bishek_now() < timedelta(hours=2):
            raise gql_error(
                error="cannot_cancel",
                message="Отменить запись можно не позднее чем за 2 часа до приёма",
            )

        booking.status = "cancelled"
        booking.cancelled_by = "client"
        booking.save(update_fields=["status", "cancelled_by", "updated_at"])
        return CancelBookingResult(ok=True, message="Запись отменена")

    @strawberry.mutation
    def error_demo(self, info: Info) -> ErrorDemo:
        """Helper mutation for testing REST-like GraphQL errors."""

        raise gql_error(error="validation_error", message="Demo error", details={"field": ["bad"]})


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[RestLikeErrorsExtension],
)
