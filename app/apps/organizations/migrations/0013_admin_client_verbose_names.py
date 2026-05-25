from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0012_services_professionals_features"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="patient",
            options={
                "verbose_name": "Клиент",
                "verbose_name_plural": "Клиенты",
            },
        ),
        migrations.AlterModelOptions(
            name="booking",
            options={
                "verbose_name": "Запись",
                "verbose_name_plural": "Записи",
            },
        ),
        migrations.AlterModelOptions(
            name="bookingservice",
            options={
                "verbose_name": "Услуга в записи",
                "verbose_name_plural": "Услуги в записи",
            },
        ),
        migrations.AlterModelOptions(
            name="review",
            options={
                "verbose_name": "Отзыв",
                "verbose_name_plural": "Отзывы",
            },
        ),
        migrations.AlterModelOptions(
            name="doctorschedule",
            options={
                "verbose_name": "Рабочее время специалиста",
                "verbose_name_plural": "Рабочее время специалистов",
            },
        ),
        migrations.AlterModelOptions(
            name="scheduleexception",
            options={
                "verbose_name": "Исключение расписания",
                "verbose_name_plural": "Исключения расписания",
            },
        ),
    ]
