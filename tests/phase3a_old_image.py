"""Stream into the exact deployed Phase 2 image against a disposable 3A DB."""
import os
import time
if os.environ.get("PHASE3A_TEST_DISPOSABLE") != "1":
    raise SystemExit("Disposable compatibility gate only")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()
from django.core.exceptions import ValidationError
from django.db import connection
from tenancy.models import Company
from tenancy.schema_verification import verify_company_schema

company = None
try:
    assert Company._meta.get_field("inventory_mode").concrete
    assert not Company.objects.exclude(inventory_mode="serial").exists()
    company = Company.objects.create(name=f"Phase3A old image {time.time_ns()}")
    company.refresh_from_db()
    assert company.inventory_mode == "serial" and company.provisioning_state == "ready"
    assert verify_company_schema(company, use_cache=False).ok
    company.contact_email = "old-image@example.com"
    company.save(update_fields=["contact_email"])
    company.refresh_from_db()
    assert company.contact_email == "old-image@example.com"
    rejected = False
    try:
        Company.objects.create(name=f"Phase3A old rejected {time.time_ns()}", inventory_mode="quantity")
    except ValidationError:
        rejected = True
    assert rejected
    print("PASS: actual deployed Phase 2 ORM reads, creates, provisions, edits and rejects quantity on forward 3A database")
finally:
    if company is not None:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(f'DROP SCHEMA {connection.ops.quote_name(company.schema_name)} CASCADE')
        company.delete()
