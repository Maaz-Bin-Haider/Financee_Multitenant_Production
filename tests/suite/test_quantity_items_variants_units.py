#!/usr/bin/env python3
"""Phase 7 quantity products, variants, SKUs, units, and HTTP checks."""

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


def product(schema, name="Mobile Phone", category="Phones"):
    return q(schema, """
        SELECT quantity_create_product(%s::jsonb)
    """, [json.dumps({
        "product_name": name,
        "category": category,
        "description": "Wholesale product",
        "user_id": 1,
    })])[0][0]


def variant_payload(product_id, unit_id, **overrides):
    payload = {
        "product_id": product_id,
        "sku": "",
        "brand": "Apple",
        "model": "iPhone 17 Pro",
        "color": "Black",
        "storage": "256GB",
        "ram": "12GB",
        "region": "Middle East",
        "condition": "New",
        "unit_id": unit_id,
        "reorder_level": "10",
        "user_id": 1,
    }
    payload.update(overrides)
    return payload


def create_variant(schema, payload):
    return q(
        schema,
        "SELECT quantity_create_variant(%s::jsonb)",
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
    user = readonly_user = None
    try:
        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE7 ITEMS {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE7 ITEMS {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)

        chk("fresh schema reaches item-master version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0]
            == definition.required_version)
        chk("fresh item-master schema verifies",
            verify_company_schema(company, use_cache=False).ok)

        expected_units = [
            ("PCS", "Piece", 0), ("BOX", "Box", 0),
            ("KG", "Kilogram", 3), ("GM", "Gram", 3),
            ("LTR", "Litre", 3), ("MTR", "Metre", 3),
        ]
        units = q(schema, """
            SELECT code, unit_name, quantity_scale
              FROM units_of_measure ORDER BY unit_id
        """)
        chk("six approved units are seeded exactly once", units == expected_units, units)
        ids = dict(q(schema, "SELECT code, unit_id FROM units_of_measure"))

        call_command(
            "apply_sql_all_tenants",
            str(definition.hardening_path),
            family=INVENTORY_MODE_QUANTITY,
            stdout=io.StringIO(),
        )
        chk("current quantity hardening preserves item master idempotently",
            q(schema, "SELECT count(*) FROM units_of_measure")[0][0] == 6
            and q(schema, """
                SELECT count(*), count(DISTINCT seed_key)
                  FROM quantity_seed_registry
            """)[0] == (14, 14))

        product_id = product(schema)
        chk("product stores normalized identity",
            q(schema, """
                SELECT normalized_name, normalized_category
                  FROM products WHERE product_id = %s
            """, [product_id])[0] == ("mobile phone", "phones"))
        chk("duplicate normalized product rejected", rejected(
            schema,
            "SELECT quantity_create_product(%s::jsonb)",
            [json.dumps({
                "product_name": "  MOBILE   PHONE ",
                "category": " phones ",
                "user_id": 1,
            })],
        ))
        chk("blank product name rejected", rejected(
            schema,
            "SELECT quantity_create_product(%s::jsonb)",
            [json.dumps({"product_name": " ", "category": "Phones"})],
        ))

        first_id = create_variant(schema, variant_payload(product_id, ids["PCS"]))
        first = q(schema, """
            SELECT sku, brand, model, color, storage, ram, region, condition
              FROM product_variants WHERE variant_id = %s
        """, [first_id])[0]
        chk("all seven required dimensions are stored",
            first[1:] == (
                "Apple", "iPhone 17 Pro", "Black", "256GB", "12GB",
                "Middle East", "New",
            ), first)
        chk("SKU is automatically suggested", first[0].startswith(
            "MOBILE-PHONE-APPLE-IPHONE-17-PRO-BLACK-256GB-12GB"
        ), first[0])

        manual_id = create_variant(schema, variant_payload(
            product_id, ids["BOX"], sku="CUSTOM.IP17.BOX",
        ))
        chk("manual SKU is accepted",
            q(schema, "SELECT sku FROM product_variants WHERE variant_id=%s",
              [manual_id])[0][0] == "CUSTOM.IP17.BOX")
        chk("same dimensions in a different unit are a distinct sellable SKU",
            manual_id != first_id)

        second_suggested = create_variant(schema, variant_payload(
            product_id, ids["KG"], reorder_level="1.234",
        ))
        second_sku = q(schema, """
            SELECT sku FROM product_variants WHERE variant_id=%s
        """, [second_suggested])[0][0]
        chk("suggested SKU collision receives deterministic suffix",
            second_sku.endswith("-2"), second_sku)
        unit_variants = {
            "PCS": first_id,
            "BOX": manual_id,
            "KG": second_suggested,
        }
        for code in ("GM", "LTR", "MTR"):
            unit_variants[code] = create_variant(
                schema,
                variant_payload(
                    product_id, ids[code], sku=f"UNIT-{code}-BOUNDARY",
                    model=f"Unit Boundary {code}", reorder_level="1.000",
                ),
            )

        chk("duplicate SKU comparison is case-insensitive", rejected(
            schema,
            "SELECT quantity_create_variant(%s::jsonb)",
            [json.dumps(variant_payload(
                product_id, ids["GM"], sku="custom.ip17.box",
            ))],
        ))
        duplicate_combo = variant_payload(
            product_id, ids["PCS"], sku="ANOTHER-SKU",
            brand=" apple ", model="IPHONE   17 PRO", color="black",
            storage="256gb", ram="12gb", region="middle east",
            condition="new",
        )
        chk("duplicate normalized combination rejected", rejected(
            schema,
            "SELECT quantity_create_variant(%s::jsonb)",
            [json.dumps(duplicate_combo)],
        ))

        for dimension in (
            "brand", "model", "color", "storage", "ram", "region", "condition",
        ):
            invalid = variant_payload(
                product_id, ids["PCS"],
                sku=f"MISSING-{dimension.upper()}",
                model=f"MODEL-{dimension}",
            )
            invalid[dimension] = " "
            chk(f"blank required {dimension} rejected", rejected(
                schema,
                "SELECT quantity_create_variant(%s::jsonb)",
                [json.dumps(invalid)],
            ))

        chk("fractional Piece reorder level rejected", rejected(
            schema,
            "SELECT quantity_create_variant(%s::jsonb)",
            [json.dumps(variant_payload(
                product_id, ids["PCS"], sku="PCS-FRACTION",
                model="Piece Fraction", reorder_level="1.001",
            ))],
        ))
        chk("fractional Box reorder level rejected", rejected(
            schema,
            "SELECT quantity_create_variant(%s::jsonb)",
            [json.dumps(variant_payload(
                product_id, ids["BOX"], sku="BOX-FRACTION",
                model="Box Fraction", reorder_level="1.5",
            ))],
        ))
        chk("three-decimal measurement accepted",
            q(schema, """
                SELECT reorder_level FROM product_variants WHERE variant_id=%s
            """, [second_suggested])[0][0] == q(
                schema, "SELECT 1.234::numeric"
            )[0][0])
        chk("four-decimal measurement rejected without rounding", rejected(
            schema,
            "SELECT quantity_create_variant(%s::jsonb)",
            [json.dumps(variant_payload(
                product_id, ids["LTR"], sku="LTR-FOUR-DECIMAL",
                model="Litre Precision", reorder_level="1.2345",
            ))],
        ))
        for code, valid, invalid in (
            ("PCS", "2", "2.001"), ("BOX", "3", "3.500"),
            ("KG", "0.001", "0.0001"), ("GM", "999.999", "1.2345"),
            ("LTR", "1.125", "1.0001"), ("MTR", "42.999", "42.9999"),
        ):
            chk(f"{code} valid quantity boundary accepted",
                not rejected(schema, """
                    SELECT quantity_validate_quantity(%s, %s)
                """, [unit_variants[code], valid]))
            chk(f"{code} invalid quantity boundary rejected", rejected(
                schema,
                "SELECT quantity_validate_quantity(%s, %s)",
                [unit_variants[code], invalid],
            ))

        q(schema, """
            SELECT quantity_update_variant(%s, %s::jsonb)
        """, [first_id, json.dumps({
            "sku": "EDITED-BEFORE-TRANSACTION",
            "unit_id": ids["KG"],
            "color": "Graphite",
            "reorder_level": "2.125",
            "user_id": 1,
        })])
        chk("SKU and unit editable before transactions",
            q(schema, """
                SELECT sku, unit_id, reorder_level FROM product_variants
                 WHERE variant_id=%s
            """, [first_id])[0] == (
                "EDITED-BEFORE-TRANSACTION", ids["KG"],
                q(schema, "SELECT 2.125::numeric")[0][0],
            ))

        q(schema, """
            INSERT INTO variant_transaction_registry (
                variant_id, source_type, source_id
            ) VALUES (%s, 'phase7_test', 1)
        """, [first_id])
        chk("SKU mutation blocked after transaction reference", rejected(
            schema,
            "SELECT quantity_update_variant(%s, %s::jsonb)",
            [first_id, json.dumps({"sku": "LOCK-BYPASS", "user_id": 1})],
        ))
        chk("unit mutation blocked after transaction reference", rejected(
            schema,
            "SELECT quantity_update_variant(%s, %s::jsonb)",
            [first_id, json.dumps({"unit_id": ids["MTR"], "user_id": 1})],
        ))
        chk("non-identity fields remain editable after transaction",
            not rejected(
                schema,
                "SELECT quantity_update_variant(%s, %s::jsonb)",
                [first_id, json.dumps({
                    "color": "Midnight Black", "reorder_level": "3.125",
                    "user_id": 1,
                })],
            ))
        q(schema, """
            SELECT quantity_update_variant(%s, '{"is_active": false}'::jsonb)
        """, [first_id])
        chk("variant can be deactivated without deletion",
            q(schema, """
                SELECT is_active FROM product_variants WHERE variant_id=%s
            """, [first_id])[0][0] is False)
        chk("active-only catalog excludes inactive variant",
            all(row[3] != first_id for row in q(
                schema, "SELECT * FROM quantity_item_catalog('', true)"
            )))
        chk("full catalog retains inactive history",
            any(row[3] == first_id for row in q(
                schema, "SELECT * FROM quantity_item_catalog('', false)"
            )))
        chk("catalog lookup finds SKU/model",
            q(schema, """
                SELECT count(*) FROM quantity_item_catalog('CUSTOM.IP17', true)
            """)[0][0] == 1)

        q(schema, """
            SELECT quantity_update_product(%s, %s::jsonb)
        """, [product_id, json.dumps({
            "product_name": "Smartphone", "category": "Mobile Phones",
            "user_id": 1,
        })])
        chk("product name/category can be updated",
            q(schema, """
                SELECT product_name, category FROM products WHERE product_id=%s
            """, [product_id])[0] == ("Smartphone", "Mobile Phones"))

        product_b = product(schema_b)
        tenant_b_variant = create_variant(
            schema_b, variant_payload(product_b, dict(
                q(schema_b, "SELECT code, unit_id FROM units_of_measure")
            )["PCS"], sku="CUSTOM.IP17.BOX"),
        )
        chk("same SKU is isolated between tenants", tenant_b_variant > 0)
        chk("tenant B cannot see tenant A variants",
            q(schema_b, "SELECT count(*) FROM product_variants")[0][0] == 1)

        user = get_user_model().objects.create_superuser(
            username=f"phase7_{TAG}",
            email=f"phase7_{TAG}@example.com",
            password="phase7-password",
        )
        Membership.objects.create(user=user, company=company)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        units_response = client.get("/items/quantity/units/")
        chk("quantity units HTTP endpoint works",
            units_response.status_code == 200
            and len(units_response.json()["units"]) == 6,
            units_response.status_code)
        catalog_response = client.get(
            "/items/quantity/catalog/", {"term": "CUSTOM.IP17"}
        )
        chk("quantity catalog/autocomplete HTTP endpoint works",
            catalog_response.status_code == 200
            and catalog_response.json()["count"] == 1,
            catalog_response.content)
        suggestion_response = client.get("/items/quantity/suggest-sku/", {
            "product_name": "Gaming Console", "brand": "Sony",
            "model": "PlayStation 6", "color": "White", "storage": "2TB",
            "ram": "32GB", "region": "Middle East", "condition": "New",
        })
        chk("SKU suggestion HTTP endpoint returns a candidate",
            suggestion_response.status_code == 200
            and suggestion_response.json()["sku"].startswith("GAMING-CONSOLE"),
            suggestion_response.content)
        missing_suggestion = client.get("/items/quantity/suggest-sku/", {
            "product_name": "Gaming Console",
        })
        chk("HTTP requires all seven variant dimensions",
            missing_suggestion.status_code == 400, missing_suggestion.status_code)

        http_product = client.post(
            "/items/quantity/products/",
            data=json.dumps({
                "product_name": "Charging Cable", "category": "Accessories",
            }),
            content_type="application/json",
        )
        chk("product can be created through quantity HTTP API",
            http_product.status_code == 201, http_product.content)
        http_product_id = http_product.json().get("product_id")
        fractional_piece = client.post(
            "/items/quantity/variants/",
            data=json.dumps(variant_payload(
                http_product_id, ids["PCS"], sku="HTTP-PCS-FRACTION",
                model="USB C", reorder_level="1.5",
            )),
            content_type="application/json",
        )
        chk("HTTP rejects fractional Piece quantity",
            fractional_piece.status_code == 400, fractional_piece.content)
        valid_measurement = client.post(
            "/items/quantity/variants/",
            data=json.dumps(variant_payload(
                http_product_id, ids["MTR"], sku="HTTP-MTR-VALID",
                model="USB C Metre", reorder_level="1.234",
            )),
            content_type="application/json",
        )
        chk("HTTP accepts three-decimal measurement quantity",
            valid_measurement.status_code == 201, valid_measurement.content)
        four_decimal = client.post(
            "/items/quantity/variants/",
            data=json.dumps(variant_payload(
                http_product_id, ids["MTR"], sku="HTTP-MTR-INVALID",
                model="USB C Long", reorder_level="1.2345",
            )),
            content_type="application/json",
        )
        chk("HTTP rejects fourth decimal without rounding",
            four_decimal.status_code == 400, four_decimal.content)
        readonly_user = get_user_model().objects.create_user(
            username=f"phase7_readonly_{TAG}",
            password="phase7-readonly-password",
        )
        readonly_user.user_permissions.add(
            Permission.objects.get(codename="view_item")
        )
        Membership.objects.create(user=readonly_user, company=company_b)
        readonly_client = Client(SERVER_NAME="localhost")
        readonly_client.force_login(readonly_user)
        chk("authorized read-only user can list quantity units",
            readonly_client.get("/items/quantity/units/").status_code == 200)
        denied_create = readonly_client.post(
            "/items/quantity/products/",
            data=json.dumps({
                "product_name": "Denied Product", "category": "Denied",
            }),
            content_type="application/json",
        )
        chk("read-only user cannot mutate quantity masters",
            denied_create.status_code == 403, denied_create.status_code)
        home_response = client.get("/home/")
        chk("unimplemented quantity routes remain gated",
            home_response.status_code == 403, home_response.status_code)
        chk("request search path resets to public",
            q("public", "SELECT current_schema()")[0][0] == "public")
    finally:
        if readonly_user:
            readonly_user.delete()
        if user:
            user.delete()
        drop_company(company_b)
        drop_company(company)

    passed = sum(ok for _name, ok, _detail in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}"
              f"{' — ' + detail if detail and not ok else ''}")
    print(f"\nQuantity items/variants/units: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
