from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import connection, transaction


@dataclass(frozen=True)
class _RenameSpec:
    from_prefix: str = "clinic_"
    to_prefix: str = "organizations_"


class Command(BaseCommand):
    help = (
        "Rename legacy 'clinic' app label to 'organizations' at DB level: "
        "tables, sequences, django_migrations, django_content_type. "
        "Idempotent (safe to run multiple times)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print SQL actions without executing",
        )

    def handle(self, *args, **options):
        dry_run: bool = bool(options.get("dry_run"))
        spec = _RenameSpec()

        with connection.cursor() as cursor, transaction.atomic():
            # 1) rename tables
            cursor.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public' AND tablename LIKE %s
                ORDER BY tablename
                """,
                [spec.from_prefix + "%"],
            )
            tables = [r[0] for r in cursor.fetchall()]

            # 2) rename sequences
            cursor.execute(
                """
                SELECT relname
                FROM pg_class
                WHERE relkind = 'S' AND relname LIKE %s
                ORDER BY relname
                """,
                [spec.from_prefix + "%"],
            )
            sequences = [r[0] for r in cursor.fetchall()]

            statements: list[str] = []

            for t in tables:
                new_name = spec.to_prefix + t[len(spec.from_prefix) :]
                # If already renamed, skip.
                if t.startswith(spec.to_prefix):
                    continue
                statements.append(f'ALTER TABLE "{t}" RENAME TO "{new_name}";')

            for s in sequences:
                new_name = spec.to_prefix + s[len(spec.from_prefix) :]
                if s.startswith(spec.to_prefix):
                    continue
                statements.append(f'ALTER SEQUENCE "{s}" RENAME TO "{new_name}";')

            # 3) update django_migrations and django_content_type (if these tables exist).
            cursor.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname='public' AND tablename IN ('django_migrations', 'django_content_type')
                """
            )
            existing_meta_tables = {r[0] for r in cursor.fetchall()}
            if "django_migrations" in existing_meta_tables:
                statements.append(
                    "UPDATE django_migrations SET app = 'organizations' WHERE app = 'clinic';"
                )
            if "django_content_type" in existing_meta_tables:
                statements.append(
                    "UPDATE django_content_type SET app_label = 'organizations' WHERE app_label = 'clinic';"
                )

            # 4) update permissions contenttype foreign keys indirectly by content_type_id,
            # no action needed if content types are updated in place.

            if dry_run:
                for st in statements:
                    self.stdout.write(st)
                self.stdout.write(self.style.WARNING("DRY RUN: no changes applied"))
                return

            for st in statements:
                self.stdout.write(st)
                cursor.execute(st)

        self.stdout.write(self.style.SUCCESS("Rename clinic -> organizations completed"))
