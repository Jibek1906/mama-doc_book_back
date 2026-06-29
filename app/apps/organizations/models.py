from datetime import datetime, timedelta
import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from api.v1.utils import label_for_day, time_range


_CYRILLIC_TO_LATIN = {
    # Russian
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    # Kyrgyz (common additions)
    "ң": "ng",
    "ө": "o",
    "ү": "u",
    "ұ": "u",
    "қ": "k",
    "һ": "h",
    "ә": "a",
    "і": "i",
}


def _transliterate_to_latin(value: str) -> str:
    """Best-effort Cyrillic -> Latin transliteration.

    This project uses human-friendly latin slugs in URLs.
    """

    if not value:
        return ""
    s = str(value)
    out = []
    for ch in s:
        lower = ch.lower()
        if lower in _CYRILLIC_TO_LATIN:
            repl = _CYRILLIC_TO_LATIN[lower]
            out.append(repl)
        else:
            out.append(ch)
    return "".join(out)


def _make_unique_slug(*, model: type[models.Model], base: str, slug_field: str = "slug") -> str:
    """Generate a unique slug for a model.

    - base: any string (name/title/full_name)
    - model: Django model class
    - slug_field: field name with uniqueness constraint
    """

    base_latin = _transliterate_to_latin(base)
    raw = slugify(base_latin, allow_unicode=False) or "item"
    slug = raw
    i = 2
    # Keep it deterministic and collision-free.
    while model.objects.filter(**{slug_field: slug}).exists():
        slug = f"{raw}-{i}"
        i += 1
    return slug


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
        verbose_name = "Специальность"
        verbose_name_plural = "Специальности"

    def __str__(self) -> str:
        return self.title


class Organization(models.Model):
    """Top-level entity (organization/salon/etc). Used by frontend to fetch project data by id."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    logo = models.ImageField(upload_to="organizations/logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    paylink_enabled = models.BooleanField(
        default=True,
        verbose_name="Paylink/оплата включены",
        help_text=(
            "Если выключить — у этой организации будет скрыта/запрещена оплата (Paylink), "
            "даже если глобально включено."
        ),
    )
    api_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name="API-ключ",
        help_text="Используется для интеграции (например, GET /partner/bookings/)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Организация"
        verbose_name_plural = "Организации"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = _make_unique_slug(model=Organization, base=self.name)
        if not self.api_key:
            import uuid
            self.api_key = str(uuid.uuid4())
        super().save(*args, **kwargs)


class Branch(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="branches"
    )
    # Which categories/specialties are available in this branch.
    specialists = models.ManyToManyField(
        "Specialist",
        blank=True,
        related_name="branches",
    )
    title = models.CharField(max_length=200, blank=True, default="")
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    # --- Payment / booking deposit ---
    paylink_enabled = models.BooleanField(
        default=False,
        verbose_name="Оплата/бронь через Paylink включена",
        help_text=(
            "Если включено — перед созданием записи требуется оплата брони. "
            "Если выключено — запись создаётся без оплаты."
        ),
    )
    paylink_amount = models.IntegerField(
        default=0,
        verbose_name="Сумма брони (KGS)",
        help_text="Сколько сом нужно оплатить для брони в этом филиале.",
    )

    paylink_token = models.TextField(
        blank=True,
        default="",
        verbose_name="Paylink токен филиала",
        help_text=(
            "Bearer token для Bakai PayLink именно для этого филиала. "
            "Если пусто — будет использован глобальный BAKAI_PAYLINK_TOKEN из .env"
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "id"]
        unique_together = ("organization", "address")
        verbose_name = "Филиал"
        verbose_name_plural = "Филиалы"

    def __str__(self) -> str:
        return f"{self.organization.name} — {self.address or self.title or self.id}"

    def save(self, *args, **kwargs):
        if not self.slug:
            # Prefer title, fallback to address, then id placeholder.
            base = self.title or self.address or f"branch-{self.organization_id or 'x'}"
            self.slug = _make_unique_slug(model=Branch, base=base)
        super().save(*args, **kwargs)


class BranchPaylinkSettings(Branch):
    """Proxy model for a dedicated admin page with PayLink settings per branch.

    This lets admin manage payment toggles without mixing it into other branch fields.
    """

    class Meta:
        proxy = True
        verbose_name = "Настройки PayLink филиала"
        verbose_name_plural = "Настройки PayLink по филиалам"


class PaymentIntent(models.Model):
    """Payment attempt / reservation.

    Flow:
    1) Front calls POST /payments/paylink with branch_id.
    2) Backend creates PaymentIntent(status=pending) and requests Bakai PayLink.
    3) Bank calls webhook -> status becomes paid/failed.
    4) Front calls POST /bookings with payment_intent_id to create booking.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_PAID, "paid"),
        (STATUS_FAILED, "failed"),
        (STATUS_EXPIRED, "expired"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="payment_intents")
    client = models.ForeignKey(
        "Client",
        on_delete=models.PROTECT,
        related_name="payment_intents",
        null=True,
        blank=True,
        help_text="Клиент (если авторизован). Может быть null, если платёж инициирован до создания клиента.",
    )
    amount = models.IntegerField()

    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    comment = models.CharField(max_length=255, blank=True, default="")

    # Bakai PayLink response
    paylink_url = models.URLField(blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    provider_payload = models.JSONField(null=True, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Оплата (Paylink)"
        verbose_name_plural = "Оплаты (Paylink)"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"PaymentIntent #{self.id} ({self.status}) {self.amount}KGS"


class BranchSchedule(models.Model):
    """Weekly working schedule for a branch (0=Mon .. 6=Sun)."""

    DOW_CHOICES = [
        (0, "Пн"),
        (1, "Вт"),
        (2, "Ср"),
        (3, "Чт"),
        (4, "Пт"),
        (5, "Сб"),
        (6, "Вс"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="schedule")
    day_of_week = models.IntegerField(choices=DOW_CHOICES)  # 0=Mon
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    is_working = models.BooleanField(default=True)

    class Meta:
        verbose_name = "График филиала"
        verbose_name_plural = "Графики филиалов"
        unique_together = ("branch", "day_of_week")

    def __str__(self) -> str:
        return f"{self.branch} — {self.day_of_week}"


class Professional(models.Model):
    CONSULTATION_CHOICES = [
        ("offline", "offline"),
        ("online", "online"),
        ("both", "both"),
    ]
    GENDER_CHOICES = [("male", "male"), ("female", "female")]

    full_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, null=True)
    photo_url = models.ImageField(upload_to="professionals/", blank=True, null=True)

    # New structure: Professional is a universal professional (barber/manicurist/doctor/etc)
    # attached to organizations via multiple branches.
    branches = models.ManyToManyField(
        Branch,
        blank=True,
        related_name="professionals",
    )

    primary_specialist = models.ForeignKey(
        Specialist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_professionals",
    )

    rating = models.DecimalField(max_digits=2, decimal_places=1, default=0.0)
    rating_count = models.IntegerField(default=0)
    experience_years = models.IntegerField(default=0)
    bio = models.TextField(blank=True)
    education = models.TextField(blank=True)

    organization_address = models.CharField(max_length=255, blank=True)
    organization_name = models.CharField(max_length=200, blank=True)
    phone_admin = models.CharField(max_length=20, blank=True)

    slot_duration_min = models.IntegerField(default=30)
    consultation_type = models.CharField(
        max_length=20, choices=CONSULTATION_CHOICES, default="offline"
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="female")
    languages = models.CharField(max_length=100, default="ru")

    is_active = models.BooleanField(default=True)
    is_accepting_new = models.BooleanField(default=True)
    paylink_enabled = models.BooleanField(
        default=True,
        verbose_name="Paylink/оплата включены",
        help_text=(
            "Если выключить — у этого врача будет скрыта/запрещена оплата (Paylink), "
            "даже если у организации и глобально включено."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Специалист"
        verbose_name_plural = "Специалисты"

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.slug and self.full_name:
            self.slug = _make_unique_slug(model=Professional, base=self.full_name)
        super().save(*args, **kwargs)

    def get_calendar(
        self,
        days: int = 30,
        *,
        duration_min: int | None = None,
        start_date=None,
    ):
        """Return availability calendar.

        - days: number of days forward
        - start_date: optional date to start from (defaults to today)
        """

        today = timezone.localtime(timezone.now()).date() if start_date is None else start_date
        result = []
        for i in range(days):
            d = today + timedelta(days=i)
            times = self._get_free_slots_for_date(d, duration_min=duration_min)
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

    def _get_free_slots_for_date(self, d, *, duration_min: int | None = None):
        exc = self.schedule_exceptions.filter(date=d).first()
        if exc and exc.is_day_off:
            return []

        dow = d.weekday()  # 0=Mon
        schedule = self.schedule.filter(day_of_week=dow, is_working=True).first()
        if not schedule and not exc:
            return []

        start_time = schedule.start_time if schedule else None
        end_time = schedule.end_time if schedule else None
        break_start = schedule.break_start if schedule else None
        break_end = schedule.break_end if schedule else None

        if exc:
            if exc.start_time:
                start_time = exc.start_time
            if exc.end_time:
                end_time = exc.end_time
            break_start = exc.break_start
            break_end = exc.break_end

        if not start_time or not end_time:
            return []

        all_slots = []
        for t in time_range(start_time, end_time, self.slot_duration_min):
            if break_start and break_end:
                if break_start <= t < break_end:
                    continue
            all_slots.append(t)

        now = timezone.localtime(timezone.now())
        if d == now.date():
            current_time = now.time()
            all_slots = [t for t in all_slots if t > current_time]

        bookings = (
            self.bookings.filter(booking_date=d)
            .exclude(status="cancelled")
            .only("booking_time", "total_duration_min")
        )
        slot_minutes = self.slot_duration_min or 30
        booked_str = set()
        for booking in bookings:
            duration = booking.total_duration_min or slot_minutes
            slots = max(1, duration // slot_minutes + (1 if duration % slot_minutes else 0))
            start_dt = timezone.datetime.combine(d, booking.booking_time)
            for i in range(slots):
                booked_str.add(
                    (start_dt + timedelta(minutes=slot_minutes * i)).strftime("%H:%M")
                )

        free_slots = [t.strftime("%H:%M") for t in all_slots if t.strftime("%H:%M") not in booked_str]

        # If client asks for a specific duration (e.g. when service takes 60 minutes),
        # hide start times where the whole duration does not fit into free consecutive slots.
        if duration_min is None:
            return free_slots
        try:
            duration_min = int(duration_min)
        except (TypeError, ValueError):
            return free_slots

        required_slots = max(
            1,
            duration_min // slot_minutes + (1 if duration_min % slot_minutes else 0),
        )
        if required_slots <= 1:
            return free_slots

        free_set = set(free_slots)

        def _add_minutes(hhmm: str, minutes: int) -> str:
            h, m = hhmm.split(":")
            base = int(h) * 60 + int(m)
            total = base + minutes
            return f"{total // 60:02d}:{total % 60:02d}"

        filtered = []
        for start in free_slots:
            ok = True
            for i in range(required_slots):
                if _add_minutes(start, slot_minutes * i) not in free_set:
                    ok = False
                    break
            if ok:
                filtered.append(start)

        return filtered


class ProfessionalAccount(models.Model):
    """Login identity for professionals (Doctor).

    Created and managed by admin. Used for professional cabinet endpoints (/v1/pro/*).
    """

    professional = models.OneToOneField(
        Professional,
        on_delete=models.CASCADE,
        related_name="account",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="professional_account",
    )
    phone = models.CharField(max_length=20, unique=True)
    username = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Аккаунт специалиста"
        verbose_name_plural = "Аккаунты специалистов"

    def __str__(self) -> str:
        return f"{self.username} ({self.phone})"


class ProfessionalSpecialty(models.Model):
    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="professional_specialties"
    )
    specialist = models.ForeignKey(
        Specialist,
        on_delete=models.CASCADE,
        related_name="professional_specialties",
        verbose_name="Специальность",
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("professional", "specialist")
        verbose_name = "Специализация специалиста"
        verbose_name_plural = "Специализации специалистов"

    def __str__(self) -> str:
        return self.specialist.title if self.specialist else "Специализация"


class Service(models.Model):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.SET_NULL,
        related_name="legacy_services",
        null=True,
        blank=True,
    )
    professionals = models.ManyToManyField(
        Professional,
        through="ProfessionalService",
        related_name="services",
        blank=True,
    )
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    duration_min = models.IntegerField(default=30)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"

    def __str__(self) -> str:
        return self.name


class ProfessionalService(models.Model):
    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="professional_services"
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="professional_services"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("professional", "service")
        verbose_name = "Услуга специалиста"
        verbose_name_plural = "Услуги специалистов"

    def __str__(self) -> str:
        return f"{self.professional} — {self.service}"


class ProjectFeatureSettings(models.Model):
    branches_enabled = models.BooleanField(
        default=True,
        verbose_name="Филиалы (адреса) включены",
        help_text="Глобальный переключатель. Если выключить — во всём проекте скрываем работу с филиалами.",
    )
    paylink_enabled = models.BooleanField(
        default=True,
        verbose_name="Paylink/оплата включены (глобально)",
        help_text=(
            "Глобальный переключатель. Если выключить — Paylink/оплата отключены для всех. "
            "Дополнительно можно отключать Paylink на уровне организации и конкретного специалиста."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки функций"
        verbose_name_plural = "Настройки функций"

    def __str__(self) -> str:
        return "Функции проекта"


class ProfessionalSchedule(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name="schedule")
    day_of_week = models.IntegerField()  # 0=Mon
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    is_working = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Рабочее время специалиста"
        verbose_name_plural = "Рабочее время специалистов"


class ScheduleException(models.Model):
    professional = models.ForeignKey(
        Professional, on_delete=models.CASCADE, related_name="schedule_exceptions"
    )
    date = models.DateField()
    is_day_off = models.BooleanField(default=True)
    reason = models.CharField(max_length=200, blank=True)
    
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Исключение расписания"
        verbose_name_plural = "Исключения расписания"


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client")
    phone = models.CharField(max_length=20, unique=True)
    photo = models.ImageField(upload_to="clients/photos/", null=True, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    inn = models.BigIntegerField(null=True, blank=True)
    nickname = models.CharField(max_length=100, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    telegram = models.CharField(max_length=100, blank=True, default="")
    instagram = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self) -> str:
        return self.full_name or self.phone

    @property
    def is_profile_completed(self) -> bool:
        return bool(self.phone)


class PendingClientProfile(models.Model):
    """Temporary token after OTP to finish client registration (step 3)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pending_profiles", null=True, blank=True)
    phone = models.CharField(max_length=20)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["token", "expires_at"])]
        verbose_name = "Токен завершения профиля клиента"
        verbose_name_plural = "Токены завершения профиля клиента"


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
    PURPOSE_PRO_LOGIN = "pro_login"

    PURPOSE_CHOICES = [
        (PURPOSE_REGISTER, PURPOSE_REGISTER),
        (PURPOSE_RESET, PURPOSE_RESET),
        (PURPOSE_LOGIN, PURPOSE_LOGIN),
        (PURPOSE_PRO_LOGIN, PURPOSE_PRO_LOGIN),
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

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="bookings")
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name="bookings")
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    payment_intent = models.OneToOneField(
        PaymentIntent,
        on_delete=models.PROTECT,
        related_name="booking",
        null=True,
        blank=True,
    )
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
        indexes = [models.Index(fields=["professional", "booking_date", "booking_time"])]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def set_services(self, services):
        BookingService.objects.filter(booking=self).delete()
        for svc in services:
            BookingService.objects.create(booking=self, service=svc, price=svc.price)


class BookingService(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="booking_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    price = models.IntegerField()

    class Meta:
        verbose_name = "Услуга в записи"
        verbose_name_plural = "Услуги в записи"


class Review(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name="reviews")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="reviews")
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT)
    client_avatar = models.CharField(max_length=255, blank=True)
    rating = models.IntegerField()
    text = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"


class PhoneCountry(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100)
    dial_code = models.CharField(max_length=10)
    flag = models.ImageField(upload_to="phone_countries/", blank=True, null=True)

    class Meta:
        ordering = ["name", "code"]

    def __str__(self) -> str:
        return f"{self.name} ({self.dial_code})"
