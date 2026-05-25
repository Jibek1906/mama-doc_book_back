import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.organizations.models import Professional


class Command(BaseCommand):
    help = "Sync professionals into Elasticsearch index"

    def add_arguments(self, parser):
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Delete and recreate professionals index before sync",
        )

    def handle(self, *args, **options):
        if not settings.ES_ENABLED:
            self.stdout.write(self.style.WARNING("ES_ENABLED=false, skip indexing"))
            return

        base = settings.ES_URL.rstrip("/")
        index = settings.ES_DOCTORS_INDEX
        timeout = settings.ES_TIMEOUT_SECONDS

        if options.get("recreate"):
            requests.delete(f"{base}/{index}", timeout=timeout)

        mapping = {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard",
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "integer"},
                    "full_name": {"type": "text"},
                    "primary_specialty": {"type": "text"},
                    "specialties": {"type": "text"},
                    "specialist_ids": {"type": "integer"},
                    "services": {"type": "text"},
                    "service_ids": {"type": "integer"},
                    "is_active": {"type": "boolean"},
                }
            },
        }

        resp = requests.put(f"{base}/{index}", json=mapping, timeout=timeout)
        if resp.status_code not in (200, 201):
            body = resp.text[:500]
            if "resource_already_exists_exception" not in body:
                raise RuntimeError(f"Failed to create index {index}: {body}")

        professionals = (
            Professional.objects.filter(is_active=True)
            .select_related("primary_specialist")
            .prefetch_related("professional_specialties__specialist", "services")
        )

        lines = []
        count = 0
        for professional in professionals:
            specialty_ids = set()
            specialty_titles = []

            if professional.primary_specialist_id:
                specialty_ids.add(professional.primary_specialist_id)
                specialty_titles.append(professional.primary_specialist.title)

            for ds in professional.professional_specialties.all():
                specialty_ids.add(ds.specialist_id)
                if ds.specialist and ds.specialist.title not in specialty_titles:
                    specialty_titles.append(ds.specialist.title)

            service_ids = []
            service_titles = []
            for service in professional.services.all():
                service_ids.append(service.id)
                service_titles.append(service.name)

            doc = {
                "id": professional.id,
                "full_name": professional.full_name,
                "primary_specialty": professional.primary_specialist.title if professional.primary_specialist_id else "",
                "specialties": specialty_titles,
                "specialist_ids": sorted(specialty_ids),
                "services": service_titles,
                "service_ids": sorted(service_ids),
                "is_active": bool(professional.is_active),
            }

            lines.append(json.dumps({"index": {"_index": index, "_id": professional.id}}, ensure_ascii=False))
            lines.append(json.dumps(doc, ensure_ascii=False))
            count += 1

        if not lines:
            self.stdout.write(self.style.WARNING("No professionals to index"))
            return

        payload = "\n".join(lines) + "\n"
        bulk = requests.post(
            f"{base}/_bulk",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
            timeout=max(timeout, 10),
        )
        bulk.raise_for_status()

        if bulk.json().get("errors"):
            raise RuntimeError("Elasticsearch bulk indexing returned errors")

        self.stdout.write(self.style.SUCCESS(f"Indexed {count} professionals into {index}"))
