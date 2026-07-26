#!/usr/bin/env python3
"""Phase 8 quantity warehouse identity, defaults, permissions, and isolation."""

import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402
from django.test import Client  # noqa: E402

from tenancy.models import (  # noqa: E402
    Company, Currency, Membership, INVENTORY_MODE_QUANTITY,
    INVENTORY_MODE_SERIAL,
)
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def q(schema, sql, params=None):
    quoted = connection.ops.quote_name(schema)
    with connection.cursor() as cur:
        cur.execute(f"SET search_path TO {quoted}, public")
        try:
            cur.execute(sql, params or [])
            return cur.fetchall() if cur.description else []
        finally:
            cur.execute("SET search_path TO public")


def rejected(schema, sql, params=None):
    try:
        with transaction.atomic():
            q(schema, sql, params)
        return False
    except DatabaseError:
        return True


def create_warehouse(schema, code, name, **extra):
    payload = {
        "warehouse_code": code,
        "warehouse_name": name,
        "address": "Karachi",
        "user_id": 1,
    }
    payload.update(extra)
    return q(
        schema,
        "SELECT quantity_create_warehouse(%s::jsonb)",
        [json.dumps(payload)],
    )[0][0]


def drop_company(company):
    if not company:
        return
    with connection.cursor() as cur:
        cur.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
        cur.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def main():
    company = company_b = None
    admin_user = readonly_user = serial_user = None
    try:
        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE8 WAREHOUSE {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE8 WAREHOUSE {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)

        chk("fresh schema reaches warehouse version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0]
            == definition.required_version)
        chk("fresh warehouse schema verifies",
            verify_company_schema(company, use_cache=False).ok)
        chk("four explicit warehouse permissions exist", set(
            Permission.objects.filter(
                codename__in=[
                    "view_warehouse", "create_warehouse",
                    "update_warehouse", "delete_warehouse",
                ]
            ).values_list("codename", flat=True)
        ) == {
            "view_warehouse", "create_warehouse",
            "update_warehouse", "delete_warehouse",
        })

        main_id = create_warehouse(schema, "MAIN", "Main Warehouse")
        chk("first active warehouse becomes default",
            q(schema, """
                SELECT is_default, is_active FROM warehouses
                 WHERE warehouse_id=%s
            """, [main_id])[0] == (True, True))
        overflow_id = create_warehouse(
            schema, "OVERFLOW", "Overflow Warehouse", address="Lahore"
        )
        chk("second warehouse is not default unless selected",
            q(schema, """
                SELECT is_default FROM warehouses WHERE warehouse_id=%s
            """, [overflow_id])[0][0] is False)
        chk("default lookup returns first warehouse",
            q(schema, "SELECT quantity_default_warehouse()")[0][0] == main_id)

        chk("duplicate normalized code rejected", rejected(
            schema,
            "SELECT quantity_create_warehouse(%s::jsonb)",
            [json.dumps({
                "warehouse_code": "main",
                "warehouse_name": "Different Name",
            })],
        ))
        chk("duplicate normalized name rejected", rejected(
            schema,
            "SELECT quantity_create_warehouse(%s::jsonb)",
            [json.dumps({
                "warehouse_code": "OTHER",
                "warehouse_name": "  MAIN   WAREHOUSE ",
            })],
        ))
        chk("blank warehouse code rejected", rejected(
            schema,
            "SELECT quantity_create_warehouse(%s::jsonb)",
            [json.dumps({
                "warehouse_code": " ", "warehouse_name": "Blank Code",
            })],
        ))
        chk("blank warehouse name rejected", rejected(
            schema,
            "SELECT quantity_create_warehouse(%s::jsonb)",
            [json.dumps({
                "warehouse_code": "BLANK", "warehouse_name": " ",
            })],
        ))
        chk("inactive warehouse cannot be requested as default", rejected(
            schema,
            "SELECT quantity_create_warehouse(%s::jsonb)",
            [json.dumps({
                "warehouse_code": "BADDEFAULT",
                "warehouse_name": "Bad Default",
                "is_active": False,
                "is_default": True,
            })],
        ))

        q(schema, """
            SELECT quantity_update_warehouse(%s, %s::jsonb)
        """, [overflow_id, json.dumps({
            "warehouse_name": "Overflow and Returns",
            "warehouse_code": "RETURNS",
            "address": "Lahore Service Centre",
            "user_id": 1,
        })])
        chk("warehouse can be renamed and recoded",
            q(schema, """
                SELECT warehouse_code, warehouse_name, address
                  FROM warehouses WHERE warehouse_id=%s
            """, [overflow_id])[0] == (
                "RETURNS", "Overflow and Returns", "Lahore Service Centre"
            ))

        q(schema, """
            SELECT quantity_update_warehouse(%s, '{"is_default": true}'::jsonb)
        """, [overflow_id])
        defaults = q(schema, """
            SELECT warehouse_id FROM warehouses
             WHERE is_default AND is_active
        """)
        chk("changing default leaves exactly one active default",
            defaults == [(overflow_id,)], defaults)
        chk("database rejects a second active default inserted directly",
            rejected(schema, """
                INSERT INTO warehouses (
                    warehouse_code, warehouse_name, is_default
                ) VALUES ('SECONDDEFAULT', 'Second Default', true)
            """))

        q(schema, """
            SELECT quantity_update_warehouse(
                %s, '{"is_active": false}'::jsonb
            )
        """, [overflow_id])
        chk("warehouse can be deactivated",
            q(schema, """
                SELECT is_active, is_default FROM warehouses
                 WHERE warehouse_id=%s
            """, [overflow_id])[0] == (False, False))
        chk("deactivating default selects active replacement",
            q(schema, "SELECT quantity_default_warehouse()")[0][0] == main_id)
        chk("active lookup excludes inactive warehouses",
            q(schema, """
                SELECT count(*) FROM quantity_warehouse_lookup('', true)
            """)[0][0] == 1)
        chk("full lookup retains inactive warehouse history",
            q(schema, """
                SELECT count(*) FROM quantity_warehouse_lookup('', false)
            """)[0][0] == 2)
        chk("lookup searches code name and address",
            q(schema, """
                SELECT warehouse_id
                  FROM quantity_warehouse_lookup('service centre', false)
            """) == [(overflow_id,)])

        q(schema, """
            INSERT INTO warehouse_reference_registry (
                warehouse_id, source_type, source_id
            ) VALUES (%s, 'phase8_test', 1)
        """, [main_id])
        chk("referenced warehouse deletion is blocked", rejected(
            schema, "SELECT quantity_delete_warehouse(%s)", [main_id]
        ))
        chk("referenced warehouse may be deactivated for new use",
            not rejected(schema, """
                SELECT quantity_update_warehouse(
                    %s, '{"is_active": false}'::jsonb
                )
            """, [main_id]))
        chk("no default is allowed when no warehouse remains active",
            q(schema, "SELECT quantity_default_warehouse()")[0][0] is None)

        q(schema, """
            SELECT quantity_update_warehouse(
                %s, '{"is_active": true, "is_default": true}'::jsonb
            )
        """, [overflow_id])
        temporary_id = create_warehouse(schema, "TEMP", "Temporary Warehouse")
        q(schema, "SELECT quantity_delete_warehouse(%s)", [temporary_id])
        chk("unreferenced warehouse may be hard-deleted",
            q(schema, """
                SELECT count(*) FROM warehouses WHERE warehouse_id=%s
            """, [temporary_id])[0][0] == 0)

        # Default deletion chooses another active warehouse.
        spare_id = create_warehouse(schema, "SPARE", "Spare Warehouse")
        q(schema, """
            SELECT quantity_update_warehouse(%s, '{"is_default": true}'::jsonb)
        """, [spare_id])
        q(schema, "SELECT quantity_delete_warehouse(%s)", [spare_id])
        chk("deleting unreferenced default selects replacement",
            q(schema, "SELECT quantity_default_warehouse()")[0][0] == overflow_id)

        same_name_b = create_warehouse(schema_b, "MAIN", "Main Warehouse")
        chk("same warehouse code/name is isolated between tenants",
            same_name_b > 0)
        chk("tenant B sees only its own warehouse",
            q(schema_b, "SELECT count(*) FROM warehouses")[0][0] == 1)

        call_command(
            "apply_sql_all_tenants",
            str(definition.hardening_path),
            family=INVENTORY_MODE_QUANTITY,
            stdout=io.StringIO(),
        )
        chk("warehouse hardening is idempotent",
            q(schema, """
                SELECT count(*) FROM quantity_seed_registry
                 WHERE seed_key='quantity.warehouse'
            """)[0][0] == 1)

        admin_user = get_user_model().objects.create_superuser(
            username=f"phase8_admin_{TAG}",
            email=f"phase8_admin_{TAG}@example.com",
            password="phase8-admin-password",
        )
        Membership.objects.create(user=admin_user, company=company)
        client = Client(SERVER_NAME="localhost")
        client.force_login(admin_user)
        page_response = client.get("/warehouses/quantity/manage/")
        chk("quantity warehouse management page renders",
            page_response.status_code == 200
            and b"Quantity Warehouses" in page_response.content
            and b"quantity_warehouses" in page_response.content,
            page_response.status_code)
        list_response = client.get("/warehouses/quantity/", {"active": "false"})
        chk("warehouse HTTP list works",
            list_response.status_code == 200
            and list_response.json()["count"] == 2,
            list_response.content)
        default_response = client.get("/warehouses/quantity/default/")
        chk("warehouse HTTP default lookup works",
            default_response.status_code == 200
            and default_response.json()["warehouse"]["warehouse_id"]
            == overflow_id,
            default_response.content)
        create_response = client.post(
            "/warehouses/quantity/create/",
            data=json.dumps({
                "warehouse_code": "HTTP",
                "warehouse_name": "HTTP Warehouse",
                "address": "Islamabad",
            }),
            content_type="application/json",
        )
        chk("warehouse HTTP creation works",
            create_response.status_code == 201, create_response.content)
        http_id = create_response.json().get("warehouse_id")
        update_response = client.post(
            f"/warehouses/quantity/{http_id}/",
            data=json.dumps({"warehouse_name": "HTTP Renamed"}),
            content_type="application/json",
        )
        chk("warehouse HTTP rename works",
            update_response.status_code == 200, update_response.content)
        delete_response = client.delete(
            f"/warehouses/quantity/{http_id}/delete/"
        )
        chk("warehouse HTTP delete works for unreferenced warehouse",
            delete_response.status_code == 200, delete_response.content)
        referenced_delete = client.delete(
            f"/warehouses/quantity/{main_id}/delete/"
        )
        chk("warehouse HTTP blocks referenced deletion",
            referenced_delete.status_code == 400, referenced_delete.content)

        readonly_user = get_user_model().objects.create_user(
            username=f"phase8_readonly_{TAG}",
            password="phase8-readonly-password",
        )
        readonly_user.user_permissions.add(
            Permission.objects.get(codename="view_warehouse")
        )
        Membership.objects.create(user=readonly_user, company=company_b)
        readonly_client = Client(SERVER_NAME="localhost")
        readonly_client.force_login(readonly_user)
        chk("warehouse viewer may list warehouses",
            readonly_client.get("/warehouses/quantity/").status_code == 200)
        denied = readonly_client.post(
            "/warehouses/quantity/create/",
            data=json.dumps({
                "warehouse_code": "DENIED",
                "warehouse_name": "Denied Warehouse",
            }),
            content_type="application/json",
        )
        chk("unauthorized warehouse mutation denied",
            denied.status_code == 403, denied.status_code)

        serial_company = Company.objects.filter(
            inventory_mode=INVENTORY_MODE_SERIAL
        ).first()
        serial_user = get_user_model().objects.create_superuser(
            username=f"phase8_serial_{TAG}",
            email=f"phase8_serial_{TAG}@example.com",
            password="phase8-serial-password",
        )
        Membership.objects.create(user=serial_user, company=serial_company)
        serial_client = Client(SERVER_NAME="localhost")
        serial_client.force_login(serial_user)
        chk("serial tenant cannot render quantity warehouse form",
            serial_client.get("/warehouses/quantity/manage/").status_code == 404)
        chk("serial tenant cannot invoke quantity warehouse SQL",
            serial_client.get("/warehouses/quantity/").status_code == 404)
        chk("unimplemented quantity home remains gated",
            client.get("/home/").status_code == 403)
        chk("request search path resets to public",
            q("public", "SELECT current_schema()")[0][0] == "public")
    finally:
        for user in (serial_user, readonly_user, admin_user):
            if user:
                user.delete()
        drop_company(company_b)
        drop_company(company)

    passed = sum(ok for _name, ok, _detail in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}"
              f"{' — ' + detail if detail and not ok else ''}")
    print(f"\nQuantity warehouses: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
