from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create default admin user in dev if it doesn't exist"

    def handle(self, *args, **options):
        username = "admin"
        password = "admin"
        email = "admin@example.com"

        if User.objects.filter(username=username).exists():
            self.stdout.write("Admin already exists")
            return

        User.objects.create_superuser(username=username, password=password, email=email)
        self.stdout.write("Created admin: admin/admin")
