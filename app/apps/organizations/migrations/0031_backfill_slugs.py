from django.db import migrations


def backfill_slugs(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Branch = apps.get_model("organizations", "Branch")
    Professional = apps.get_model("organizations", "Professional")

    # Importing from current models is ok in data migration as long as we
    # don't touch historical model state. Here we only need helper function.
    from apps.organizations.models import _make_unique_slug

    for org in Organization.objects.filter(slug__isnull=True).only("id", "name", "slug"):
        org.slug = _make_unique_slug(model=Organization, base=org.name)
        org.save(update_fields=["slug"])

    for br in Branch.objects.filter(slug__isnull=True).only("id", "title", "address", "organization_id", "slug"):
        base = br.title or br.address or f"branch-{br.organization_id or 'x'}"
        br.slug = _make_unique_slug(model=Branch, base=base)
        br.save(update_fields=["slug"])

    for pro in Professional.objects.filter(slug__isnull=True).only("id", "full_name", "slug"):
        pro.slug = _make_unique_slug(model=Professional, base=pro.full_name)
        pro.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0030_branchpaylinksettings_branch_slug_organization_slug_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
    ]
