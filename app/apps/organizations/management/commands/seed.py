from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.color import no_style
from django.db import connection, transaction
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from apps.organizations.models import (
    Booking,
    BookingService,
    Branch,
    Professional,
    ProfessionalSchedule,
    ProfessionalSpecialty,
    Organization,
    OTPCode,
    Client,
    PhoneCountry,
    ProfessionalService,
    ProjectFeatureSettings,
    Review,
    SMSCode,
    Service,
    Specialist,
    BranchSchedule,
)


SPECIALISTS = [
    ("Акушер", "akusher", "Специалист по ведению беременности и родов"),
    ("Аллерголог", "allergolog", "Диагностика и лечение аллергических заболеваний"),
    ("Анестезиолог", "anesteziolog", "Обеспечение анестезии при хирургических вмешательствах"),
    ("Стоматолог", "stomatolog", "Лечение и профилактика заболеваний зубов"),
    ("Дерматолог", "dermatolog", "Лечение заболеваний кожи, волос и ногтей"),
    ("Эндокринолог", "endokrinolog", "Диагностика и лечение болезней эндокринной системы"),
    ("Физиотерапевт", "fizioterapevt", "Восстановительное лечение физическими факторами"),
    ("Гастроэнтеролог", "gastroenterolog", "Диагностика и лечение болезней ЖКТ"),
    ("Хирург", "hirurg", "Хирургическое лечение различных заболеваний"),
    ("Кардиолог", "kardiolog", "Диагностика и лечение болезней сердца"),
    ("ЛОР", "lor", "Лечение болезней уха, горла и носа"),
    ("Нейрохирург", "neyrohirurg", "Хирургическое лечение болезней нервной системы"),
    ("Офтальмолог", "oftalmolog", "Диагностика и лечение болезней глаз"),
    ("Онколог", "onkolog", "Диагностика и лечение онкологических заболеваний"),
    ("Ортодонт", "ortodont", "Исправление прикуса и выравнивание зубов"),
    ("Психиатр", "psihiatr", "Диагностика и лечение психических расстройств"),
    ("Ревматолог", "revmatolog", "Лечение болезней суставов и соединительной ткани"),
    ("Терапевт", "terapevt", "Первичная диагностика и лечение внутренних болезней"),
    (
        "Венеролог",
        "venerolog",
        "Диагностика и лечение инфекций, передаваемых половым путём",
    ),

    # --- НЕ-медицинские категории (салон/beauty) ---
    ("Маникюр", "manikur", "Маникюр и уход за ногтями"),
    ("Педикюр", "pedikur", "Педикюр и уход за стопами"),
    ("Парикмахер", "parikmaher", "Стрижки и укладки"),
    ("Барбер", "barber", "Мужские стрижки и борода"),
    ("Бровист", "brovist", "Коррекция и окрашивание бровей"),
    ("Косметолог", "kosmetolog", "Уходовые и косметологические процедуры"),
    ("Массажист", "massazhist", "Массаж и SPA-процедуры"),
    ("Лэшмейкер", "lashmaker", "Наращивание и ламинирование ресниц"),
    ("Визажист", "vizazhist", "Макияж и подготовка образа"),
    ("Тренер", "trener", "Индивидуальные и групповые тренировки"),
]


# В моках фронта имена файлов картинок местами не совпадают со slug.
# Чтобы при подключении к API картинки открывались, кладём их в backend static
# и отдаём URL вида /static/images/...
ICON_FILENAME_BY_SLUG = {
    "akusher": "akusher.png",
    "allergolog": "allergolog.png",
    "anesteziolog": "anastetika.png",
    "stomatolog": "dentist.png",
    "dermatolog": "dermatolog.png",
    "endokrinolog": "endokrinolog.png",
    "fizioterapevt": "fizioterapeft.png",
    "gastroenterolog": "gastro.png",
    "hirurg": "hirurg.png",
    "kardiolog": "kardiolog.png",
    "lor": "lor.png",
    "neyrohirurg": "neirohirurg.png",
    "oftalmolog": "oftalmolog.png",
    "onkolog": "onkolog.png",
    "ortodont": "ortodont.png",
    "psihiatr": "psihiatr.png",
    "revmatolog": "revmatolog.png",
    "terapevt": "terapeft.png",
    "venerolog": "venerolog.png",

    # Seed-only category icon (not present in the original icon set)
    "ginekolog": "ginekolog.svg",
}


def _icon_for_slug(slug: str) -> str:
    """Return backend static icon path if we have it, else empty string."""

    filename = ICON_FILENAME_BY_SLUG.get(slug)
    if not filename:
        return ""
    return f"/static/images/specialists/{filename}"


class Command(BaseCommand):
    help = "Clear demo domain data and seed organizations, branches, professionals, services, schedules and reviews"

    def _reset_sequences(self):
        models = [
            Review,
            Booking,
            ProfessionalService,
            Service,
            ProfessionalSchedule,
            ProfessionalSpecialty,
            Professional,
            Branch,
            Organization,
            Specialist,
            PhoneCountry,
            OTPCode,
            SMSCode,
            Client,
            ProjectFeatureSettings,
        ]
        sql_list = connection.ops.sequence_reset_sql(no_style(), models)
        with connection.cursor() as cursor:
            for sql in sql_list:
                cursor.execute(sql)

    @transaction.atomic
    def handle(self, *args, **options):
        # Start fresh for demo data (safe for dev/stage): clear domain tables.
        # Staff/superuser accounts are kept; demo client users are recreated below.
        Review.objects.all().delete()
        Booking.objects.all().delete()
        ProfessionalService.objects.all().delete()
        Service.objects.all().delete()
        ProfessionalSchedule.objects.all().delete()
        ProfessionalSpecialty.objects.all().delete()
        Professional.objects.all().delete()
        Branch.objects.all().delete()
        Organization.objects.all().delete()
        Specialist.objects.all().delete()
        PhoneCountry.objects.all().delete()
        OTPCode.objects.all().delete()
        SMSCode.objects.all().delete()
        Client.objects.all().delete()
        User.objects.filter(is_staff=False, is_superuser=False).delete()
        ProjectFeatureSettings.objects.all().delete()
        self._reset_sequences()

        specialists_by_slug = {}
        for idx, (title, slug, desc) in enumerate(SPECIALISTS, start=1):
            obj, _ = Specialist.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "description": desc,
                    "icon_url": _icon_for_slug(slug),
                    "sort_order": idx,
                    "is_active": True,
                },
            )
            specialists_by_slug[slug] = obj

        # скрытые специализации (нужны, чтобы совпасть с текущими моками врачей)
        gyn, _ = Specialist.objects.update_or_create(
            slug="ginekolog",
            defaults={
                "title": "Гинеколог",
                "description": "",
                "icon_url": _icon_for_slug("ginekolog"),
                "sort_order": 999,
                # IMPORTANT: must be visible in /v1/specialists for frontend filtering
                "is_active": True,
            },
        )
        gyn_endo, _ = Specialist.objects.update_or_create(
            slug="ginekolog-endokrinolog",
            defaults={
                "title": "Гинеколог-эндокринолог",
                "description": "",
                "icon_url": "",
                "sort_order": 1000,
                "is_active": False,
            },
        )

        # Professionals (universal): doctors + beauty etc
        professionals = [
            {
                "id": 1,
                "full_name": "Сурапбеков Бекмамат Султангазиевич",
                "photo_url": "/images/doctors/1.jpg",
                "primary": "ginekolog",
                "extra_specialties": ["ginekolog-endokrinolog"],
                "rating": 4.8,
                "rating_count": 127,
                "experience_years": 12,
                "bio": "Опытный специалист в области гинекологии и гинекологической эндокринологии. Ведёт приём взрослых клиентов, специализируется на лечении бесплодия и гормональных нарушений.",
                "education": "КГМА им. И.К. Ахунбаева, 2010 г. Ординатура по акушерству и гинекологии.",
                "clinic_name": "МедЦентр Плюс",
                "clinic_address": "Орозбекова 112, Бишкек",
                "branch_title": "Главный филиал",
                "schedule": (time(8, 30), time(17, 30), time(12, 30), time(13, 30), [0, 1, 2, 3, 4]),
                "consultation_type": "offline",
                "gender": "male",
                "languages": "ru,kg",
            },
            {
                "id": 2,
                "full_name": "Адьлбекова Алина Адьлбековна",
                "photo_url": "/images/doctors/2.jpg",
                "primary": "fizioterapevt",
                "extra_specialties": [],
                "rating": 4.9,
                "rating_count": 45,
                "experience_years": 8,
                "bio": "Специалист по физиотерапии и мануальной терапии. Помогает клиентам с болями в спине, суставах и последствиями травм.",
                "education": "КРСУ им. Б.Н. Ельцина, 2016 г. Специальность: восстановительная медицина.",
                "clinic_name": "Клиника Здоровье",
                "clinic_address": "ул. Киевская 77, Бишкек",
                "branch_title": "Центр",
                "schedule": (time(9, 0), time(18, 0), time(13, 0), time(14, 0), [0, 1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 3,
                "full_name": "Буудайбекова Мээрим Улановна",
                "photo_url": "/images/doctors/3.jpg",
                "primary": "fizioterapevt",
                "extra_specialties": [],
                "rating": 5.0,
                "rating_count": 12,
                "experience_years": 5,
                "bio": "Молодой и перспективный специалист, работает с клиентами после операций и травм. Применяет современные методики ЛФК и физиолечения.",
                "education": "КГМА им. И.К. Ахунбаева, 2019 г. Специальность: лечебное дело.",
                "clinic_name": "Реабилитационный центр Vita",
                "clinic_address": "пр. Манаса 40, Бишкек",
                "branch_title": "Vita Манаса",
                "schedule": (time(10, 0), time(19, 0), time(14, 0), time(15, 0), [1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 4,
                "full_name": "Князев Игорь Алексеевич",
                "photo_url": "/images/doctors/4.jpg",
                "primary": "fizioterapevt",
                "extra_specialties": [],
                "rating": 4.7,
                "rating_count": 89,
                "experience_years": 15,
                "bio": "Ведущий физиотерапевт с 15-летним стажем. Специализируется на лечении хронических заболеваний опорно-двигательного аппарата.",
                "education": "Первый МГМУ им. Сеченова (Москва), 2009 г.",
                "clinic_name": "МедЦентр Плюс",
                "clinic_address": "Орозбекова 112, Бишкек",
                "branch_title": "Главный филиал",
                "schedule": (time(9, 0), time(16, 0), time(12, 0), time(13, 0), [0, 2, 4]),
                "consultation_type": "both",
                "gender": "male",
                "languages": "ru",
            },
            {
                "id": 5,
                "full_name": "Тынарбекова Жылдыз Эмилбековна",
                "photo_url": "/images/doctors/5.jpg",
                "primary": "fizioterapevt",
                "extra_specialties": [],
                "rating": 4.8,
                "rating_count": 34,
                "experience_years": 10,
                "bio": "Сертифицированный массажист и физиотерапевт. Работает с болями в спине, шейным остеохондрозом и послеродовым восстановлением.",
                "education": "Бишкекский медицинский колледж, 2014 г.",
                "clinic_name": "Студия массажа Body&Soul",
                "clinic_address": "ул. Токтогула 210, Бишкек",
                "branch_title": "Body&Soul Токтогула",
                "schedule": (time(11, 0), time(20, 0), time(15, 0), time(16, 0), [0, 1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },

            # salon / beauty
            {
                "id": 6,
                "full_name": "Айдана Н. (Маникюр)",
                "photo_url": "/images/doctors/6.jpg",
                "primary": "manikur",
                "extra_specialties": ["pedikur"],
                "rating": 4.9,
                "rating_count": 21,
                "experience_years": 7,
                "bio": "Мастер маникюра и педикюра. Аппаратный/комбинированный маникюр, покрытие и дизайн.",
                "education": "Курсы Nail Pro, 2018 г.",
                "clinic_name": "Nail Studio Shine",
                "clinic_address": "ул. Киевская 120, Бишкек",
                "branch_title": "Shine Center",
                "schedule": (time(10, 0), time(21, 0), time(14, 0), time(15, 0), [0, 1, 2, 3, 4, 5, 6]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 7,
                "full_name": "Руслан К. (Барбер)",
                "photo_url": "/images/doctors/4.jpg",
                "primary": "barber",
                "extra_specialties": ["parikmaher"],
                "rating": 4.8,
                "rating_count": 57,
                "experience_years": 9,
                "bio": "Барбер. Мужские стрижки, оформление бороды и бритьё.",
                "education": "Barber Academy, 2016 г.",
                "clinic_name": "Barber House",
                "clinic_address": "пр. Чуй 15, Бишкек",
                "branch_title": "Barber House Чуй",
                "schedule": (time(10, 0), time(22, 0), time(15, 0), time(16, 0), [0, 1, 2, 3, 4, 5, 6]),
                "consultation_type": "offline",
                "gender": "male",
                "languages": "ru",
            },
            {
                "id": 8,
                "full_name": "Алия С. (Бровист)",
                "photo_url": "/images/doctors/2.jpg",
                "primary": "brovist",
                "extra_specialties": ["kosmetolog"],
                "rating": 4.7,
                "rating_count": 18,
                "experience_years": 4,
                "bio": "Коррекция/окрашивание бровей, ламинирование, уходовые процедуры.",
                "education": "Beauty School, 2021 г.",
                "clinic_name": "Beauty Point",
                "clinic_address": "ул. Токтогула 88, Бишкек",
                "branch_title": "Beauty Point Центр",
                "schedule": (time(9, 30), time(19, 30), time(13, 30), time(14, 30), [1, 2, 3, 4, 5, 6]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 9,
                "full_name": "Медер Т. (Массажист)",
                "photo_url": "/static/images/doctors/7.jpg",
                "primary": "massazhist",
                "extra_specialties": [],
                "rating": 4.8,
                "rating_count": 32,
                "experience_years": 6,
                "bio": "Массажист SPA-направления: расслабляющие, спортивные и восстановительные программы.",
                "education": "SPA Academy Bishkek, 2020 г.",
                "clinic_name": "Aroma SPA",
                "clinic_address": "ул. Исанова 55, Бишкек",
                "branch_title": "Aroma SPA Исанова",
                "schedule": (time(12, 0), time(21, 0), time(16, 0), time(17, 0), [0, 1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "male",
                "languages": "ru,kg",
            },
            {
                "id": 10,
                "full_name": "Элина К. (Лэшмейкер)",
                "photo_url": "/static/images/doctors/8.jpg",
                "primary": "lashmaker",
                "extra_specialties": ["brovist"],
                "rating": 4.9,
                "rating_count": 44,
                "experience_years": 5,
                "bio": "Наращивание ресниц, ламинирование и аккуратный уход после процедуры.",
                "education": "Lash Lab, 2021 г.",
                "clinic_name": "Beauty Point",
                "clinic_address": "ул. Токтогула 88, Бишкек",
                "branch_title": "Beauty Point Центр",
                "schedule": (time(10, 0), time(20, 0), time(14, 0), time(15, 0), [0, 1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 11,
                "full_name": "София М. (Визажист)",
                "photo_url": "/static/images/doctors/2.jpg",
                "primary": "vizazhist",
                "extra_specialties": ["kosmetolog"],
                "rating": 4.7,
                "rating_count": 25,
                "experience_years": 4,
                "bio": "Дневной, вечерний и свадебный макияж, подготовка кожи и образа.",
                "education": "Makeup Studio Pro, 2022 г.",
                "clinic_name": "Lumi Beauty",
                "clinic_address": "ул. Ахунбаева 100, Бишкек",
                "branch_title": "Lumi Beauty Юг",
                "schedule": (time(9, 0), time(18, 0), time(13, 0), time(14, 0), [2, 3, 4, 5, 6]),
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru",
            },
            {
                "id": 12,
                "full_name": "Бакыт А. (Тренер)",
                "photo_url": "/static/images/doctors/1.jpg",
                "primary": "trener",
                "extra_specialties": [],
                "rating": 4.8,
                "rating_count": 39,
                "experience_years": 8,
                "bio": "Персональные тренировки, функциональная подготовка и восстановление после нагрузок.",
                "education": "Fitness Coach School, 2018 г.",
                "clinic_name": "FitLab",
                "clinic_address": "пр. Манаса 12, Бишкек",
                "branch_title": "FitLab Манаса",
                "schedule": (time(7, 0), time(15, 0), time(11, 0), time(12, 0), [0, 1, 2, 3, 4, 5]),
                "consultation_type": "offline",
                "gender": "male",
                "languages": "ru,kg",
            },
        ]

        for d in professionals:
            org_name = (d.get("clinic_name") or "").strip() or "Без организации"
            address = (d.get("clinic_address") or "").strip()
            org, _ = Organization.objects.get_or_create(name=org_name)
            branch, _ = Branch.objects.get_or_create(
                organization=org,
                address=address,
                defaults={"title": d.get("branch_title", "")},
            )
            if d.get("branch_title") and branch.title != d["branch_title"]:
                branch.title = d["branch_title"]
                branch.save(update_fields=["title"])

            photo_url = d["photo_url"]
            if photo_url.startswith("/images/"):
                photo_url = photo_url.replace("/images/", "/static/images/", 1)

            professional, _ = Professional.objects.update_or_create(
                id=d["id"],
                defaults={
                    "full_name": d["full_name"],
                    "photo_url": photo_url,
                    "primary_specialist": gyn
                    if d["primary"] == "ginekolog"
                    else specialists_by_slug.get(d["primary"]),
                    "rating": d["rating"],
                    "rating_count": d["rating_count"],
                    "experience_years": d["experience_years"],
                    "bio": d["bio"],
                    "education": d["education"],
                    "organization_name": d["clinic_name"],
                    "organization_address": d["clinic_address"],
                    "slot_duration_min": 30,
                    "consultation_type": d.get("consultation_type", "offline"),
                    "is_accepting_new": True,
                    "is_active": True,
                    "gender": d["gender"],
                    "languages": d["languages"],
                },
            )

            # Attach to branch/org (Doctor.branches is M2M). This is required for:
            # - /professionals?organization_id
            # - /organizations/* counts
            # - /services?organization_id
            professional.branches.add(branch)

            # Branch should know which categories are present.
            if professional.primary_specialist_id:
                branch.specialists.add(professional.primary_specialist)

            if professional.primary_specialist_id:
                ProfessionalSpecialty.objects.update_or_create(
                    professional=professional,
                    specialist=professional.primary_specialist,
                    defaults={"is_primary": True},
                )

            for extra_slug in d.get("extra_specialties", []):
                extra = specialists_by_slug.get(extra_slug)
                if extra_slug == "ginekolog-endokrinolog":
                    extra = gyn_endo
                if extra:
                    ProfessionalSpecialty.objects.update_or_create(
                        professional=professional,
                        specialist=extra,
                        defaults={"is_primary": False},
                    )
                    branch.specialists.add(extra)

            start_time, end_time, break_start, break_end, working_days = d.get(
                "schedule",
                (time(9, 0), time(18, 0), time(13, 0), time(14, 0), [0, 1, 2, 3, 4]),
            )
            for dow in range(7):
                ProfessionalSchedule.objects.update_or_create(
                    professional=professional,
                    day_of_week=dow,
                    defaults={
                        "start_time": start_time,
                        "end_time": end_time,
                        "break_start": break_start,
                        "break_end": break_end,
                        "is_working": dow in working_days,
                    },
                )

                # Keep branch schedule in sync (rough demo): take the first professional as a source.
                BranchSchedule.objects.update_or_create(
                    branch=branch,
                    day_of_week=dow,
                    defaults={
                        "start_time": start_time if dow in working_days else None,
                        "end_time": end_time if dow in working_days else None,
                        "break_start": break_start if dow in working_days else None,
                        "break_end": break_end if dow in working_days else None,
                        "is_working": dow in working_days,
                    },
                )

        # services (3-7 на каждого врача по ТЗ)
        def svc(professional_id: int, name: str, price: int, duration_min: int):
            professional = Professional.objects.get(id=professional_id)
            service, _ = Service.objects.update_or_create(
                professional=professional,
                name=name,
                defaults={"price": price, "duration_min": duration_min, "is_active": True},
            )
            ProfessionalService.objects.update_or_create(
                professional=professional,
                service=service,
                defaults={"is_active": True},
            )

        svc(1, "Общий осмотр", 1500, 30)
        svc(1, "Осмотр в зеркалах", 1500, 20)
        svc(1, "Сдача анализов", 1500, 15)
        svc(1, "Планирование семьи", 1500, 40)
        svc(1, "Лечение бесплодия", 1500, 60)
        svc(1, "Сбор анамнеза", 1500, 20)

        svc(2, "Первичная консультация", 1200, 30)
        svc(2, "Мануальная терапия", 2500, 45)
        svc(2, "Лечебный массаж", 2000, 60)

        svc(3, "ЛФК сессия", 1000, 45)
        svc(3, "Электрофорез", 800, 20)
        svc(3, "Ультразвуковая терапия", 1100, 30)

        svc(4, "Прием врача", 2000, 30)
        svc(4, "Физиопроцедуры", 1800, 40)
        svc(4, "Контрольный осмотр", 1500, 20)

        svc(5, "Массаж спины", 1800, 60)
        svc(5, "Массаж шейно-воротниковой зоны", 1600, 40)
        svc(5, "Реабилитационный курс", 2200, 50)

        # salon services
        svc(6, "Маникюр (комбинированный)", 1200, 60)
        svc(6, "Педикюр (аппаратный)", 1800, 90)
        svc(6, "Покрытие гель-лак", 900, 30)

        svc(7, "Мужская стрижка", 1000, 45)
        svc(7, "Оформление бороды", 800, 30)
        svc(7, "Королевское бритьё", 1200, 45)

        svc(8, "Коррекция бровей", 700, 30)
        svc(8, "Окрашивание бровей", 600, 30)
        svc(8, "Ламинирование бровей", 1500, 60)

        svc(9, "Классический массаж", 2200, 60)
        svc(9, "Спортивный массаж", 2600, 60)
        svc(9, "SPA-программа", 3500, 90)

        svc(10, "Наращивание ресниц", 2200, 120)
        svc(10, "Ламинирование ресниц", 1800, 75)
        svc(10, "Снятие ресниц", 500, 30)

        svc(11, "Дневной макияж", 1800, 60)
        svc(11, "Вечерний макияж", 2500, 90)
        svc(11, "Свадебный образ", 5000, 150)

        svc(12, "Персональная тренировка", 1500, 60)
        svc(12, "Функциональная диагностика", 1000, 45)
        svc(12, "План тренировок", 2000, 60)

        # 5-10 отзывов на каждого врача
        patients = []
        for idx, name in enumerate(
            [
                "Самат Досалиев",
                "Айгуль М.",
                "Нурсултан Т.",
                "Жылдыз К.",
                "Алина С.",
                "Айбек О.",
                "Канат Р.",
                "Диана Ж.",
                "Эркин Б.",
                "Мээрим Л.",
            ],
            start=1,
        ):
            phone = f"+9967000000{idx:02d}"
            user, _ = User.objects.get_or_create(username=phone)
            patient, _ = Client.objects.update_or_create(
                user=user,
                defaults={"phone": phone, "full_name": name},
            )
            patients.append(patient)

        review_texts = [
            "Очень внимательный врач, всё подробно объяснил.",
            "Приём прошёл комфортно, рекомендую.",
            "Понравилось отношение и подробные рекомендации.",
            "Доктор всё объяснил и помог разобраться.",
            "Спасибо за профессионализм и заботу.",
            "Быстрое и понятное объяснение лечения.",
            "Клиника чистая, врач компетентный.",
            "Остался доволен консультацией.",
            "Назначенное лечение помогло.",
            "Врач уделил много внимания деталям.",
        ]

        # Reviews must be tied to real completed bookings, but these seed bookings
        # should not block the current/future calendar. Keep them in the past and
        # use stable confirmation codes so repeated seed runs are deterministic.
        base_review_date = timezone.localdate() - timedelta(days=30)
        for professional in Professional.objects.all().order_by("id"):
            for i in range(5):
                booking_dt = datetime.combine(base_review_date, time(9, 0)) + timedelta(
                    minutes=30 * i
                )
                patient = patients[(professional.id + i) % len(patients)]
                booking, _ = Booking.objects.update_or_create(
                    confirmation_code=f"TG{professional.id:02d}{i:03d}",
                    defaults={
                        "professional": professional,
                        "client": patient,
                        "booking_date": base_review_date,
                        "booking_time": booking_dt.time(),
                        "status": "completed",
                        "total_price": 1500,
                        "total_duration_min": 30,
                    },
                )
                Review.objects.update_or_create(
                    booking=booking,
                    defaults={
                        "professional": professional,
                        "client": patient,
                        "rating": 5 - (i % 2),
                        "text": review_texts[(professional.id + i) % len(review_texts)],
                        "is_approved": True,
                    },
                )

        PhoneCountry.objects.update_or_create(
            code="KG",
            defaults={"name": "Кыргызстан", "dial_code": "+996"},
        )
        PhoneCountry.objects.update_or_create(
            code="RU",
            defaults={"name": "Россия", "dial_code": "+7"},
        )
        PhoneCountry.objects.update_or_create(
            code="KZ",
            defaults={"name": "Казахстан", "dial_code": "+7"},
        )

        ProjectFeatureSettings.objects.create(branches_enabled=True, paylink_enabled=True)

        # If Elasticsearch is enabled, keep search index in sync for frontend.
        try:
            if getattr(settings, "ES_ENABLED", False):
                from django.core.management import call_command

                call_command("sync_doctors_es")
        except Exception:
            # ES is optional; seed must stay usable without it.
            pass

        self.stdout.write(self.style.SUCCESS("Seed done"))
