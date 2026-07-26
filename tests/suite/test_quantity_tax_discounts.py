#!/usr/bin/env python3
"""Phase 17 tax/discount calculation and tenant-boundary checks."""
import json
import io
import os
import sys
import time
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()

from django.db import DatabaseError, connection, transaction
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from tenancy.models import (
    Company, Currency, Membership, INVENTORY_MODE_QUANTITY,
)
from tenancy.schema_verification import verify_company_schema
from tenancy.schema_families import schema_family
from tests.suite.test_quantity_purchases import setup_scope
from tests.suite.test_quantity_sale_returns import account

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def check(name, outcome):
    RESULTS.append((name, bool(outcome)))


def query(schema, sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(
            f"SET search_path TO {connection.ops.quote_name(schema)}, public"
        )
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchall() if cursor.description else []
        finally:
            cursor.execute("SET search_path TO public")


def calculate(schema, payload):
    value = query(
        schema, "SELECT quantity_calculate_document(%s::jsonb)",
        [json.dumps(payload)],
    )[0][0]
    return json.loads(value) if isinstance(value, str) else value


def rejected(schema, payload):
    try:
        with transaction.atomic():
            calculate(schema, payload)
        return False
    except DatabaseError:
        return True


def drop(company):
    if not company:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
        cursor.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def main():
    taxable = non_tax = user = None
    try:
        currency = Currency.objects.get(pk="PKR")
        taxable = Company.objects.create(
            name=f"PH17 {TAG} Tax", inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="tax",
        )
        non_tax = Company.objects.create(
            name=f"PH17 {TAG} Non Tax", inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="non_tax",
        )
        schema = taxable.schema_name
        check("fresh schema reaches tax version",
              query(schema, "SELECT version FROM tenant_schema_metadata")[0][0] == 13)
        check("tax environment is provisioned",
              query(schema, "SELECT tax_environment FROM tenant_schema_metadata")[0][0] == "tax")
        check("schema verifies", verify_company_schema(taxable, use_cache=False).ok)
        code = query(
            schema, "SELECT quantity_upsert_tax_code(%s::jsonb)",
            [json.dumps({"code": "GST18", "name": "GST 18%",
                         "rate_percent": "18"})],
        )[0][0]
        code = json.loads(code) if isinstance(code, str) else code
        tax_id = code["tax_code_id"]
        zero_code = query(
            schema, "SELECT quantity_upsert_tax_code(%s::jsonb)",
            [json.dumps({"code": "ZERO", "name": "Zero Rate",
                         "rate_percent": "0"})],
        )[0][0]
        zero_code = json.loads(zero_code) if isinstance(zero_code, str) else zero_code
        full_code = query(
            schema, "SELECT quantity_upsert_tax_code(%s::jsonb)",
            [json.dumps({"code": "FULL", "name": "One Hundred Percent",
                         "rate_percent": "100"})],
        )[0][0]
        full_code = json.loads(full_code) if isinstance(full_code, str) else full_code
        exclusive = calculate(schema, {
            "tax_mode": "exclusive", "invoice_discount_type": "fixed",
            "invoice_discount_value": "10", "minor_units": 2,
            "lines": [
                {"quantity": "2", "unit_price": "100",
                 "discount_type": "percent", "discount_value": "10",
                 "tax_classification": "taxable", "tax_code_id": tax_id},
                {"quantity": "1", "unit_price": "100",
                 "tax_classification": "taxable", "tax_code_id": tax_id},
            ],
        })
        check("discount order and exclusive tax are exact",
              Decimal(str(exclusive["subtotal_base"])) == Decimal("300")
              and Decimal(str(exclusive["line_discount_total_base"])) == Decimal("20")
              and Decimal(str(exclusive["invoice_discount_total_base"])) == Decimal("10")
              and Decimal(str(exclusive["tax_total_base"])) == Decimal("48.60")
              and Decimal(str(exclusive["total_base"])) == Decimal("318.60"))
        allocations = [Decimal(str(line["invoice_discount_base"]))
                       for line in exclusive["lines"]]
        check("invoice discount allocation reconciles exactly",
              sum(allocations) == Decimal("10"))
        inclusive = calculate(schema, {
            "tax_mode": "inclusive", "lines": [{
                "quantity": "1", "unit_price": "118",
                "tax_classification": "taxable", "tax_code_id": tax_id,
            }],
        })
        check("inclusive tax is extracted",
              Decimal(str(inclusive["tax_total_base"])) == Decimal("18")
              and Decimal(str(inclusive["total_base"])) == Decimal("118"))
        edge_matrix = calculate(schema, {
            "tax_mode": "exclusive", "invoice_discount_type": "fixed",
            "invoice_discount_value": "0.01", "lines": [
                {"quantity": "1", "unit_price": "0.03",
                 "tax_classification": "zero_rated",
                 "tax_code_id": zero_code["tax_code_id"]},
                {"quantity": "1", "unit_price": "0.03",
                 "tax_classification": "exempt",
                 "exemption_reference": "SCHEDULE-EX"},
                {"quantity": "1", "unit_price": "1",
                 "discount_type": "fixed", "discount_value": "0.01",
                 "tax_classification": "taxable",
                 "tax_code_id": full_code["tax_code_id"]},
            ],
        })
        check("zero-rated exempt fixed-discount and 100% tax matrix reconciles",
              sum(Decimal(str(x["invoice_discount_base"]))
                  for x in edge_matrix["lines"]) == Decimal("0.01")
              and Decimal(str(edge_matrix["tax_total_base"])) == Decimal("0.98")
              and Decimal(str(edge_matrix["total_base"])) == Decimal("2.02"))
        query(schema, "UPDATE tax_codes SET rate_percent=20 WHERE tax_code_id=%s",
              [tax_id])
        check("calculation output is a historical snapshot",
              Decimal(str(exclusive["lines"][0]["tax_rate_percent"]))
              == Decimal("18"))
        base_line = {"quantity": "1", "unit_price": "100"}
        check("non-tax company calculates zero tax",
              Decimal(str(calculate(non_tax.schema_name,
                  {"lines": [base_line]})["tax_total_base"])) == 0)
        taxed_line = dict(base_line, tax_classification="taxable", tax_code_id=tax_id)
        check("non-tax company rejects tax", rejected(
            non_tax.schema_name, {"lines": [taxed_line]}))
        check("negative discount rejected", rejected(
            schema, {"lines": [dict(base_line, discount_type="fixed",
                                     discount_value="-1",
                                     tax_classification="exempt",
                                     exemption_reference="EX")]}))
        check("excessive discount rejected", rejected(
            schema, {"invoice_discount_type": "fixed",
                     "invoice_discount_value": "101",
                     "lines": [dict(base_line, tax_classification="exempt",
                                    exemption_reference="EX")]}))
        check("100 percent discount is supported",
              Decimal(str(calculate(schema, {
                  "lines": [dict(base_line, discount_type="percent",
                                 discount_value="100",
                                 tax_classification="exempt",
                                 exemption_reference="EX")]
              })["total_base"])) == 0)
        variant, warehouse = setup_scope(schema, "TAXPOST", "PCS")
        user = get_user_model().objects.create_superuser(
            username=f"p17_{TAG}", email="p17@example.com", password="pass"
        )
        Membership.objects.create(user=user, company=taxable)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        purchase_payload = {
            "action": "submit", "idempotency_key": f"pur-{TAG}",
            "invoice_date": "2026-07-20", "vendor_name": "Tax Vendor",
            "purchase_type": "credit", "tax_mode": "exclusive",
            "invoice_discount_type": "fixed",
            "invoice_discount_value": "100", "items": [{
                "variant_id": variant, "warehouse_id": warehouse,
                "quantity": "10", "unit_cost_base": "100",
                "discount_type": "percent", "discount_value": "10",
                "tax_classification": "taxable", "tax_code_id": tax_id,
            }],
        }
        purchase_response = client.post(
            "/purchase/purchasing/", data=json.dumps(purchase_payload),
            content_type="application/json",
        )
        purchase_result = purchase_response.json()
        if purchase_response.status_code != 200:
            print("Purchase posting response:", purchase_result)
        check("taxed discounted purchase posts atomically",
              purchase_response.status_code == 200
              and Decimal(str(purchase_result["total_base"])) == Decimal("960"))
        purchase_id = purchase_result.get("purchase_invoice_id")
        purchase_row = query(schema, """
            SELECT subtotal_base,line_discount_total_base,
                   invoice_discount_total_base,tax_total_base,total_base,
                   tax_journal_id
              FROM purchase_invoices WHERE purchase_invoice_id=%s
        """, [purchase_id])[0] if purchase_id else None
        check("purchase calculation snapshot persists",
              purchase_row is not None and purchase_row[:5] == (
                  Decimal("1000"), Decimal("100"), Decimal("100"),
                  Decimal("160"), Decimal("960"),
              ) and purchase_row[5] is not None)
        check("purchase tax journal reconciles control and payable",
              account(schema, "1400") == Decimal("800")
              and account(schema, "1300") == Decimal("160")
              and account(schema, "2000") == Decimal("-960"))
        sale_payload = {
            "action": "submit", "idempotency_key": f"sal-{TAG}",
            "invoice_date": "2026-07-21", "customer_name": "Tax Customer",
            "sale_type": "credit", "tax_mode": "exclusive",
            "invoice_discount_type": "fixed", "invoice_discount_value": "20",
            "items": [{
                "variant_id": variant, "warehouse_id": warehouse,
                "quantity": "2", "unit_price_base": "200",
                "discount_type": "none", "discount_value": "0",
                "tax_classification": "taxable", "tax_code_id": tax_id,
            }],
        }
        sale_response = client.post(
            "/sale/sales/", data=json.dumps(sale_payload),
            content_type="application/json",
        )
        sale_result = sale_response.json()
        check("taxed discounted sale posts atomically",
              sale_response.status_code == 200
              and Decimal(str(sale_result["total_base"])) == Decimal("456"))
        check("sale tax journal reconciles control and receivable",
              account(schema, "4000") == Decimal("-380")
              and account(schema, "2100") == Decimal("-76")
              and account(schema, "1200") == Decimal("456"))
        page = client.get("/purchase/purchasing/")
        check("tax controls render for tax company",
              page.status_code == 200 and b"Tax Mode" in page.content
              and b"GST18" in page.content
              and b"Tax Code Administration" in page.content)
        admin_tax_response = client.post(
            "/purchase/quantity-tax-codes/", data=json.dumps({
                "code": "ZEROADMIN", "name": "Administrative Zero Rate",
                "rate_percent": "0", "purchase_account_code": "1300",
                "sale_account_code": "2100", "is_active": True,
            }), content_type="application/json",
        )
        check("authorized tenant admin can configure tax code",
              admin_tax_response.status_code == 200
              and admin_tax_response.json()["code"] == "ZEROADMIN")
        sale_line_id = query(
            schema, "SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",
            [sale_result["sale_invoice_id"]],
        )[0][0]
        sale_return_response = client.post(
            "/saleReturn/create-sale-return/", data=json.dumps({
                "action": "submit", "idempotency_key": f"sr-{TAG}",
                "return_date": "2026-07-22", "customer_name": "Tax Customer",
                "items": [{"source_sale_line_id": sale_line_id,
                           "quantity": "1"}],
            }), content_type="application/json",
        )
        sale_return_result = sale_return_response.json()
        check("partial sale return reverses historical tax proportionally",
              sale_return_response.status_code == 200
              and Decimal(str(sale_return_result["tax_reversal_base"]))
              == Decimal("38")
              and account(schema, "2100") == Decimal("-38")
              and account(schema, "1200") == Decimal("228"))
        sale_return_reverse = client.post(
            "/saleReturn/create-sale-return/", data=json.dumps({
                "action": "reverse",
                "sale_return_id": sale_return_result["sale_return_id"],
            }), content_type="application/json",
        )
        check("sale-return reversal restores tax control balances",
              sale_return_reverse.status_code == 200
              and account(schema, "2100") == Decimal("-76")
              and account(schema, "1200") == Decimal("456"))
        purchase_line_id = query(
            schema, """SELECT purchase_line_id FROM purchase_lines
                       WHERE purchase_invoice_id=%s""",
            [purchase_result["purchase_invoice_id"]],
        )[0][0]
        purchase_return_response = client.post(
            "/purchaseReturn/create-purchase-return/", data=json.dumps({
                "action": "submit", "idempotency_key": f"pr-{TAG}",
                "return_date": "2026-07-23", "vendor_name": "Tax Vendor",
                "items": [{"source_purchase_line_id": purchase_line_id,
                           "quantity": "1"}],
            }), content_type="application/json",
        )
        purchase_return_result = purchase_return_response.json()
        check("partial purchase return reverses historical tax proportionally",
              purchase_return_response.status_code == 200
              and Decimal(str(purchase_return_result["tax_reversal_base"]))
              == Decimal("16")
              and account(schema, "1300") == Decimal("144")
              and account(schema, "2000") == Decimal("-864"))
        purchase_return_reverse = client.post(
            "/purchaseReturn/create-purchase-return/", data=json.dumps({
                "action": "reverse",
                "purchase_return_id":
                    purchase_return_result["purchase_return_id"],
            }), content_type="application/json",
        )
        check("purchase-return reversal restores tax control balances",
              purchase_return_reverse.status_code == 200
              and account(schema, "1300") == Decimal("160")
              and account(schema, "2000") == Decimal("-960"))
        reverse_response = client.post(
            "/sale/sales/", data=json.dumps({
                "action": "reverse", "sale_id": sale_result["sale_invoice_id"]
            }), content_type="application/json",
        )
        check("sale reversal reverses base and tax journals",
              reverse_response.status_code == 200
              and account(schema, "4000") == 0
              and account(schema, "2100") == 0
              and account(schema, "1200") == 0)
        call_command(
            "apply_sql_all_tenants",
            str(schema_family(INVENTORY_MODE_QUANTITY).hardening_path),
            family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO(),
        )
        check("existing-tenant rollout preserves public tax environment",
              query(schema, """SELECT tax_environment
                               FROM tenant_schema_metadata""")[0][0] == "tax"
              and verify_company_schema(taxable, use_cache=False).ok)
    finally:
        if user:
            user.delete()
        drop(non_tax)
        drop(taxable)
    passed = sum(ok for _, ok in RESULTS)
    for name, ok in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"\nQuantity tax/discount engine: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
