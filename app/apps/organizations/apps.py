from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # python import path
    name = "apps.organizations"
    # app_label (affects admin URLs + contenttypes + migrations state)
    label = "organizations"
    verbose_name = "Организации / Специалисты / Клиенты"
