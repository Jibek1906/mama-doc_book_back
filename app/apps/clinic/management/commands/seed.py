from datetime import time

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from apps.clinic.models import (
    Doctor,
    DoctorSchedule,
    DoctorSpecialty,
    Patient,
    PhoneCountry,
    Review,
    Service,
    Specialist,
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
}


class Command(BaseCommand):
    help = "Seed initial specialists/doctors/services/schedules/reviews"

    def handle(self, *args, **options):
        specialists_by_slug = {}
        for idx, (title, slug, desc) in enumerate(SPECIALISTS, start=1):
            icon_filename = ICON_FILENAME_BY_SLUG.get(slug, f"{slug}.png")
            obj, _ = Specialist.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "description": desc,
                    "icon_url": f"/static/images/specialists/{icon_filename}",
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
                "icon_url": "",
                "sort_order": 999,
                "is_active": False,
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

        # Несколько врачей под текущий фронт
        doctors = [
            {
                "id": 1,
                "full_name": "Сурапбеков Бекмамат Султангазиевич",
                "photo_url": "/images/doctors/1.jpg",
                "primary": "ginekolog",
                "extra_specialties": ["ginekolog-endokrinolog"],
                "rating": 4.8,
                "rating_count": 127,
                "experience_years": 12,
                "bio": "Опытный специалист в области гинекологии и гинекологической эндокринологии. Ведёт приём взрослых пациентов, специализируется на лечении бесплодия и гормональных нарушений.",
                "education": "КГМА им. И.К. Ахунбаева, 2010 г. Ординатура по акушерству и гинекологии.",
                "clinic_name": "МедЦентр Плюс",
                "clinic_address": "Орозбекова 112, Бишкек",
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
                "bio": "Специалист по физиотерапии и мануальной терапии. Помогает пациентам с болями в спине, суставах и последствиями травм.",
                "education": "КРСУ им. Б.Н. Ельцина, 2016 г. Специальность: восстановительная медицина.",
                "clinic_name": "Клиника Здоровье",
                "clinic_address": "ул. Киевская 77, Бишкек",
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
                "bio": "Молодой и перспективный специалист, работает с пациентами после операций и травм. Применяет современные методики ЛФК и физиолечения.",
                "education": "КГМА им. И.К. Ахунбаева, 2019 г. Специальность: лечебное дело.",
                "clinic_name": "Реабилитационный центр Vita",
                "clinic_address": "пр. Манаса 40, Бишкек",
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
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
            {
                "id": 6,
                "full_name": "Исаева Айсулуу Камиловна",
                "photo_url": "/images/doctors/6.jpg",
                "primary": "fizioterapevt",
                "extra_specialties": [],
                "rating": 4.9,
                "rating_count": 21,
                "experience_years": 7,
                "bio": "Специалист по восстановительной медицине. Проводит комплексные программы реабилитации после травм и операций.",
                "education": "КГМА им. И.К. Ахунбаева, 2017 г.",
                "clinic_name": "Клиника Здоровье",
                "clinic_address": "ул. Киевская 77, Бишкек",
                "consultation_type": "offline",
                "gender": "female",
                "languages": "ru,kg",
            },
        ]

        for d in doctors:
            doc, _ = Doctor.objects.update_or_create(
                id=d["id"],
                defaults={
                    "full_name": d["full_name"],
                    "photo_url": f"/static/images/doctors/{d['id']}.jpg",
                    "primary_specialist": gyn
                    if d["primary"] == "ginekolog"
                    else specialists_by_slug.get(d["primary"]),
                    "rating": d["rating"],
                    "rating_count": d["rating_count"],
                    "experience_years": d["experience_years"],
                    "bio": d["bio"],
                    "education": d["education"],
                    "clinic_name": d["clinic_name"],
                    "clinic_address": d["clinic_address"],
                    "slot_duration_min": 30,
                    "consultation_type": d.get("consultation_type", "offline"),
                    "is_accepting_new": True,
                    "is_active": True,
                    "gender": d["gender"],
                    "languages": d["languages"],
                },
            )

            if doc.primary_specialist_id:
                DoctorSpecialty.objects.get_or_create(
                    doctor=doc,
                    specialist=doc.primary_specialist,
                    defaults={"is_primary": True},
                )

            for extra_slug in d.get("extra_specialties", []):
                extra = specialists_by_slug.get(extra_slug)
                if extra_slug == "ginekolog-endokrinolog":
                    extra = gyn_endo
                if extra:
                    DoctorSpecialty.objects.get_or_create(
                        doctor=doc,
                        specialist=extra,
                        defaults={"is_primary": False},
                    )

            # график: Пн+Ср 09-18, обед 13-14
            # чтобы календарь не был пустым в любой день недели — делаем 7/7.
            for dow in range(7):
                DoctorSchedule.objects.get_or_create(
                    doctor=doc,
                    day_of_week=dow,
                    defaults={
                        "start_time": time(9, 0),
                        "end_time": time(18, 0),
                        "break_start": time(13, 0),
                        "break_end": time(14, 0),
                        "is_working": True,
                    },
                )

        # services (как в моках)
        def svc(doctor_id: int, name: str, price: int, duration_min: int):
            doctor = Doctor.objects.get(id=doctor_id)
            Service.objects.update_or_create(
                doctor=doctor,
                name=name,
                defaults={"price": price, "duration_min": duration_min, "is_active": True},
            )

        svc(1, "Общий осмотр", 1500, 30)
        svc(1, "Осмотр в зеркалах", 1500, 20)
        svc(1, "Сдача анализов", 1500, 15)
        svc(1, "Планирование семьи", 1500, 40)
        svc(1, "Лечение бесплодия", 1500, 60)
        svc(1, "Сбор анамнеза", 1500, 20)

        svc(2, "Первичная консультация", 1200, 30)
        svc(2, "Мануальная терапия", 2500, 45)

        svc(3, "ЛФК сессия", 1000, 45)
        svc(3, "Электрофорез", 800, 20)

        svc(4, "Прием врача", 2000, 30)

        svc(5, "Массаж спины", 1800, 60)

        svc(6, "Консультация", 1300, 30)

        # минимальные reviews (а reviews.total_count отдаем из doctor.rating_count)
        p1_user, _ = User.objects.get_or_create(username="+996700000001")
        p1, _ = Patient.objects.get_or_create(
            user=p1_user,
            defaults={"phone": "+996700000001", "full_name": "Самат Досалиев"},
        )
        p2_user, _ = User.objects.get_or_create(username="+996700000002")
        p2, _ = Patient.objects.get_or_create(
            user=p2_user,
            defaults={"phone": "+996700000002", "full_name": "Айгуль М."},
        )

        doc1 = Doctor.objects.get(id=1)
        Review.objects.get_or_create(
            doctor=doc1,
            patient=p1,
            defaults={
                "rating": 5,
                "text": "Очень внимательный врач, всё подробно объяснил. Рекомендую!",
                "is_approved": True,
            },
        )
        Review.objects.get_or_create(
            doctor=doc1,
            patient=p2,
            defaults={
                "rating": 5,
                "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
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

        self.stdout.write(self.style.SUCCESS("Seed done"))
