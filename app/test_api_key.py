import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.organizations.models import Organization

orgs = Organization.objects.all()
for org in orgs:
    print(f"ID: {org.id}, Name: {org.name}, Active: {org.is_active}, API_KEY: '{org.api_key}'")

