#!/usr/bin/env python3
"""
Deep transaction lifecycle regression tests for Financee tenants.

This script targets the real-world serial state flows that are easy to break:

* purchase -> sale -> sale return -> sale again -> sale return -> purchase return
* purchase invoice price-only updates when some serials are already sold
* replacing only unsold purchase serials while sold serials stay unchanged
* blocking removal/replacement of sold serials
* partial returns across multi-serial invoices
* sale-return update/delete safety after resale
* sale invoice update/delete safety after returns exist
* cash-sale returns versus credit-sale returns
* multi-item invoices with mixed serial states
* blocking duplicate sales/returns and wrong-party returns
* executing the accounting, stock, monthly, sales, and dashboard report surface
  after each posted entry

Run inside the web container:

    docker compose -f deploy/docker-compose.yml exec web \
      python tests/test_transaction_lifecycle_deep.py

Optional:

    RUN_TAG=manual1 python tests/test_transaction_lifecycle_deep.py

The test creates uniquely named records and intentionally leaves the accounting
trail in place.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass

import psycopg2
from psycopg2 import extensions


RUN_TAG = os.environ.get("RUN_TAG") or time.strftime("%Y%m%d%H%M%S")

DSN = {
    "dbname": os.environ.get("DB_NAME", "financee"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
}


@dataclass
class Result:
    section: str
    name: str
    ok: bool
    detail: str = ""


class DeepLifecycleRunner:
    def __init__(self, conn, schema: str, user_id: int):
        self.conn = conn
        self.schema = schema
        self.user_id = user_id
        self.results: list[Result] = []
        self.report_failures: list[Result] = []
        self.ctx: dict[str, object] = {}
        suffix = f"{schema}_{RUN_TAG}".upper()
        self.vendor = f"DEEP VENDOR {suffix}"
        self.vendor_2 = f"DEEP VENDOR 2 {suffix}"
        self.customer = f"DEEP CUSTOMER {suffix}"
        self.customer_2 = f"DEEP CUSTOMER 2 {suffix}"
        self.expense = f"DEEP EXPENSE {suffix}"
        self.item = f"DEEP ITEM {suffix}"
        self.item_2 = f"DEEP ITEM 2 {suffix}"
        self.serials = [f"{suffix}-SN-{i:04d}" for i in range(1, 41)]
        self.days = [
            "2025-07-01",
            "2025-07-02",
            "2025-07-03",
            "2025-07-04",
            "2025-07-05",
            "2025-07-06",
            "2025-07-07",
        ]

    def cursor(self):
        if self.conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
            self.conn.rollback()
        cur = self.conn.cursor()
        cur.execute(f'SET search_path TO "{self.schema}", public')
        return cur

    def record(self, section: str, name: str, ok: bool, detail: str = ""):
        self.results.append(Result(section, name, ok, detail))

    def step(self, section, name, sql, params=None, expect_error=False):
        cur = None
        try:
            cur = self.cursor()
            if expect_error:
                cur.execute("BEGIN")
            cur.execute(sql, params or [])
            row = cur.fetchone()
            value = row[0] if row else None
            if expect_error:
                cur.execute("ROLLBACK")
                self.record(section, name, False, "Expected an error, but the query succeeded.")
            else:
                self.record(section, name, True)
            return value
        except Exception as exc:
            if expect_error and cur is not None:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
            try:
                self.conn.rollback()
            except Exception:
                pass
            if expect_error:
                self.record(section, name, True, f"Blocked as expected: {exc}")
            else:
                self.record(section, name, False, f"{type(exc).__name__}: {exc}")
            return None
        finally:
            if cur is not None:
                cur.close()

    def fetch_one(self, sql, params=None):
        cur = self.cursor()
        try:
            cur.execute(sql, params or [])
            return cur.fetchone()
        finally:
            cur.close()

    def assert_true(self, section, name, condition, detail=""):
        self.record(section, name, bool(condition), "" if condition else detail)

    def party_id(self, name):
        row = self.fetch_one("SELECT party_id FROM parties WHERE party_name=%s", [name])
        return row[0] if row else None

    def sale_return_id_for_serial(self, serial):
        row = self.fetch_one(
            """
            SELECT sri.sales_return_id
            FROM salesreturnitems sri
            WHERE sri.serial_number=%s
            ORDER BY sri.sales_return_item_id DESC
            LIMIT 1
            """,
            [serial],
        )
        return row[0] if row else None

    def sale_invoice_exists(self, invoice_id):
        row = self.fetch_one("SELECT count(*) FROM salesinvoices WHERE sales_invoice_id=%s", [invoice_id])
        return bool(row and row[0])

    def sale_return_exists(self, return_id):
        row = self.fetch_one("SELECT count(*) FROM salesreturns WHERE sales_return_id=%s", [return_id])
        return bool(row and row[0])

    def purchase_item_payload(self, serials, unit_price=100, item_name=None):
        return [
            {
                "item_name": item_name or self.item,
                "qty": len(serials),
                "unit_price": unit_price,
                "serials": [{"serial": s, "comment": "deep lifecycle"} for s in serials],
            }
        ]

    def sale_item_payload(self, serials, unit_price=150, item_name=None):
        return [
            {
                "item_name": item_name or self.item,
                "qty": len(serials),
                "unit_price": unit_price,
                "serials": serials,
            }
        ]

    def serial_stock(self, serial):
        row = self.fetch_one("SELECT in_stock FROM purchaseunits WHERE serial_number=%s", [serial])
        return row[0] if row else None

    def active_sold_count(self, serial):
        row = self.fetch_one(
            """
            SELECT count(*)
            FROM soldunits su
            JOIN purchaseunits pu ON pu.unit_id = su.unit_id
            WHERE pu.serial_number=%s AND su.status='Sold'
            """,
            [serial],
        )
        return int(row[0]) if row else 0

    def assert_stock(self, section, serial, expected):
        actual = self.serial_stock(serial)
        self.assert_true(
            section,
            f"{serial} in_stock={expected}",
            actual is expected,
            f"Expected in_stock={expected}, got {actual}.",
        )

    def setup_master_data(self):
        section = "00 setup"
        for party_type, name in (
            ("Vendor", self.vendor),
            ("Vendor", self.vendor_2),
            ("Customer", self.customer),
            ("Customer", self.customer_2),
            ("Expense", self.expense),
        ):
            payload = {
                "party_name": name,
                "party_type": party_type,
                "opening_balance": 0,
                "balance_type": "Debit",
                "created_by_id": str(self.user_id),
            }
            self.step(section, f"add party {name}", "SELECT add_party_from_json(%s::jsonb)", [json.dumps(payload)])

        if self.party_id("Cash Sale") is None:
            payload = {
                "party_name": "Cash Sale",
                "party_type": "Customer",
                "opening_balance": 0,
                "balance_type": "Debit",
                "created_by_id": str(self.user_id),
            }
            self.step(section, "add required Cash Sale party", "SELECT add_party_from_json(%s::jsonb)", [json.dumps(payload)])
        self.assert_true(section, "Cash Sale party exists", self.party_id("Cash Sale") is not None)

        for item, price in ((self.item, 250), (self.item_2, 500)):
            payload = {
                "item_name": item,
                "sale_price": price,
                "storage": "DEEP-WH",
                "created_by_id": str(self.user_id),
            }
            self.step(section, f"add item {item}", "SELECT add_item_from_json(%s::jsonb)", [json.dumps(payload)])

        self.run_reports("after setup")

    def run_reports(self, checkpoint):
        """Exercise every report family after each transaction checkpoint."""
        section = f"reports: {checkpoint}"
        f, t = self.days[0], self.days[-1]
        existing_serial = self.serials[0]
        report_calls = [
            # accounts reports
            ("trial balance json", "SELECT get_trial_balance_json()", []),
            ("trial balance view", "SELECT * FROM vw_trial_balance", []),
            ("detailed ledger customer", "SELECT * FROM detailed_ledger(%s,%s,%s)", [self.customer, f, t]),
            ("detailed ledger2 customer", "SELECT * FROM detailed_ledger2(%s,%s,%s)", [self.customer, f, t]),
            ("detailed ledger vendor", "SELECT * FROM detailed_ledger(%s,%s,%s)", [self.vendor, f, t]),
            ("cash ledger", "SELECT * FROM get_cash_ledger_with_party(%s,%s)", [f, t]),
            ("accounts receivable", "SELECT get_accounts_receivable_json_excluding()", []),
            ("accounts payable", "SELECT get_accounts_payable_json_excluding()", []),
            ("party balances", "SELECT get_party_balances_json()", []),
            ("expense balances", "SELECT get_expense_party_balances_json()", []),
            # stock reports
            ("stock summary function", "SELECT * FROM stock_summary()", []),
            ("stock report view", "SELECT * FROM stock_report", []),
            ("stock worth report", "SELECT * FROM stock_worth_report", []),
            ("item history", "SELECT * FROM item_transaction_history(%s::text,%s::date,%s::date)", [self.item, f, t]),
            ("item detail", "SELECT * FROM get_item_stock_by_name(%s)", [self.item]),
            ("item last purchase", "SELECT * FROM item_last_purchase_view", []),
            ("item last sale", "SELECT * FROM item_last_sale_view", []),
            ("serial ledger", "SELECT * FROM get_serial_ledger(%s)", [existing_serial]),
            ("serial ledger purchase", "SELECT * FROM get_serial_ledger_purchase(%s)", [existing_serial]),
            ("serial ledger sales", "SELECT * FROM get_serial_ledger_sales(%s)", [existing_serial]),
            ("serial details", "SELECT * FROM get_serial_number_details(%s)", [existing_serial]),
            # monthly reports
            ("monthly company position", "SELECT monthly_company_position(%s)", [t]),
            ("monthly income statement", "SELECT monthly_income_statement(%s,%s)", [f, t]),
            ("period close preview", "SELECT preview_period_close(%s,%s)", [2025, 7]),
            # sales reports
            ("sales summary json", "SELECT sales_summary_json(%s,%s)", [f, t]),
            ("product profitability json", "SELECT product_profitability_json(%s,%s)", [f, t]),
            ("customer profitability json", "SELECT customer_profitability_json(%s,%s)", [f, t]),
            ("sales by product json", "SELECT sales_by_product_json(%s,%s)", [f, t]),
            ("sales by customer json", "SELECT sales_by_customer_json(%s,%s)", [f, t]),
            ("sale-wise profit json", "SELECT sale_wise_profit_json(%s,%s)", [f, t]),
            ("sales trend json", "SELECT sales_trend_json(%s,%s,%s)", [f, t, "day"]),
            ("invoice register json", "SELECT invoice_register_json(%s,%s)", [f, t]),
            ("legacy sale-wise profit function", "SELECT * FROM sale_wise_profit(%s,%s)", [f, t]),
            ("legacy sale-wise profit view", "SELECT * FROM sale_wise_profit_view", []),
            ("legacy company worth view", "SELECT * FROM standing_company_worth_view", []),
            # dashboard report APIs
            ("dash sales today", "SELECT fn_dash_sales_today_kpi()", []),
            ("dash sales last7", "SELECT fn_dash_sales_last7days()", []),
            ("dash sales range", "SELECT fn_dash_sales_range(%s,%s)", [f, t]),
            ("dash stock kpi", "SELECT fn_dash_stock_kpi()", []),
            ("dash low stock", "SELECT fn_dash_low_stock_items(%s)", [5]),
            ("dash fast moving", "SELECT fn_dash_fast_moving_items(%s,%s)", [30, 10]),
            ("dash stale stock", "SELECT fn_dash_stale_stock(%s)", [30]),
            ("dash top customers", "SELECT fn_dash_top_customers(%s,%s,%s)", [5, f, t]),
            ("dash top vendors", "SELECT fn_dash_top_vendors(%s,%s,%s)", [5, f, t]),
            ("dash receivables aging", "SELECT fn_dash_receivables_aging()", []),
            ("dash recent transactions", "SELECT fn_dash_recent_transactions(%s)", [10]),
            ("dash expense kpi", "SELECT fn_dash_expense_kpi()", []),
            ("dash expense categories", "SELECT fn_dash_top_expense_categories(%s,%s,%s)", [5, f, t]),
            ("dash expense descriptions", "SELECT fn_dash_top_expense_descriptions(%s,%s,%s)", [5, f, t]),
            ("dash smart alerts", "SELECT fn_dash_smart_alerts()", []),
        ]

        before = len(self.results)
        for name, sql, params in report_calls:
            self.step(section, name, sql, params)
        for result in self.results[before:]:
            if not result.ok:
                self.report_failures.append(result)
        self.assert_basic_invariants(section)

    def assert_basic_invariants(self, section):
        row = self.fetch_one("SELECT count(*) FROM journalentries je WHERE NOT EXISTS (SELECT 1 FROM journallines jl WHERE jl.journal_id=je.journal_id)")
        self.assert_true(section, "no empty journal entries", row and row[0] == 0, f"Empty journal entries found: {row}.")

        for serial in self.serials:
            active = self.active_sold_count(serial)
            self.assert_true(section, f"{serial} has at most one active sale", active <= 1, f"Active sold rows: {active}.")

    def test_purchase_sale_return_resale_purchase_return(self):
        section = "01 lifecycle"
        vendor_id = self.party_id(self.vendor)
        customer_id = self.party_id(self.customer)

        purchase_id = self.step(
            section,
            "purchase four serials",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(self.purchase_item_payload(self.serials[:4], 100)), self.user_id],
        )
        self.ctx["purchase_id"] = purchase_id
        for serial in self.serials[:4]:
            self.assert_stock(section, serial, True)
        self.run_reports("after initial purchase")

        sale_id = self.step(
            section,
            "sell serial 1",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(self.sale_item_payload([self.serials[0]], 150)), self.user_id],
        )
        self.ctx["sale_id_1"] = sale_id
        self.assert_stock(section, self.serials[0], False)
        self.run_reports("after first sale")

        self.step(
            section,
            "duplicate sale blocked",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(self.sale_item_payload([self.serials[0]], 155)), self.user_id],
            expect_error=True,
        )

        self.step(
            section,
            "wrong customer sale return blocked",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer_2, json.dumps([self.serials[0]]), self.user_id],
            expect_error=True,
        )

        self.step(
            section,
            "sale return serial 1",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([self.serials[0]]), self.user_id],
        )
        self.assert_stock(section, self.serials[0], True)
        self.run_reports("after first sale return")

        self.step(
            section,
            "duplicate sale return blocked",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([self.serials[0]]), self.user_id],
            expect_error=True,
        )

        self.step(
            section,
            "resell returned serial 1",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[2], json.dumps(self.sale_item_payload([self.serials[0]], 180)), self.user_id],
        )
        self.assert_stock(section, self.serials[0], False)
        self.run_reports("after resale")

        self.step(
            section,
            "second sale return serial 1",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([self.serials[0]]), self.user_id],
        )
        self.assert_stock(section, self.serials[0], True)
        self.run_reports("after second sale return")

        self.step(
            section,
            "wrong vendor purchase return blocked",
            "SELECT create_purchase_return(%s,%s::jsonb,%s)",
            [self.vendor_2, json.dumps([self.serials[0]]), self.user_id],
            expect_error=True,
        )

        self.step(
            section,
            "purchase return serial 1 after lifecycle",
            "SELECT create_purchase_return(%s,%s::jsonb,%s)",
            [self.vendor, json.dumps([self.serials[0]]), self.user_id],
        )
        self.assert_stock(section, self.serials[0], False)
        self.run_reports("after purchase return of lifecycle serial")

        self.step(
            section,
            "sale after purchase return blocked",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[3], json.dumps(self.sale_item_payload([self.serials[0]], 190)), self.user_id],
            expect_error=True,
        )

    def test_mixed_purchase_update_corrections(self):
        section = "02 mixed purchase update"
        vendor_id = self.party_id(self.vendor)
        customer_id = self.party_id(self.customer)
        base_serials = self.serials[4:8]
        sold = base_serials[0]
        unsold_replace = base_serials[3]
        replacement = self.serials[8]

        purchase_id = self.step(
            section,
            "purchase mixed-state invoice",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(self.purchase_item_payload(base_serials, 200)), self.user_id],
        )
        self.ctx["mixed_purchase_id"] = purchase_id
        self.run_reports("after mixed purchase")

        self.step(
            section,
            "sell one serial from mixed invoice",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(self.sale_item_payload([sold], 300)), self.user_id],
        )
        self.assert_stock(section, sold, False)
        self.run_reports("after mixed invoice sale")

        price_update_payload = self.purchase_item_payload(base_serials, 225)
        validation = self.step(
            section,
            "validate price-only update with sold serial",
            "SELECT validate_purchase_update2(%s,%s::jsonb)",
            [purchase_id, json.dumps(price_update_payload)],
        )
        data = json.loads(validation) if isinstance(validation, str) else validation
        self.assert_true(
            section,
            "price-only validation is allowed",
            isinstance(data, dict) and data.get("is_valid") is True,
            f"Validation failed: {data}",
        )
        self.step(
            section,
            "apply price-only update with sold serial",
            "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
            [purchase_id, json.dumps(price_update_payload), self.vendor, self.days[0], self.user_id],
        )
        self.assert_stock(section, sold, False)
        self.run_reports("after price-only purchase update")

        replace_unsold_serials = [base_serials[0], base_serials[1], base_serials[2], replacement]
        replace_payload = self.purchase_item_payload(replace_unsold_serials, 225)
        validation = self.step(
            section,
            "validate replacing only unsold serial",
            "SELECT validate_purchase_update2(%s,%s::jsonb)",
            [purchase_id, json.dumps(replace_payload)],
        )
        data = json.loads(validation) if isinstance(validation, str) else validation
        self.assert_true(
            section,
            "unsold-only replacement validation is allowed",
            isinstance(data, dict) and data.get("is_valid") is True,
            f"Validation failed: {data}",
        )
        self.step(
            section,
            "apply replacing only unsold serial",
            "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
            [purchase_id, json.dumps(replace_payload), self.vendor, self.days[0], self.user_id],
        )
        self.assert_stock(section, sold, False)
        self.assert_stock(section, unsold_replace, None)
        self.assert_stock(section, replacement, True)
        self.run_reports("after unsold serial replacement")

        remove_sold_payload = self.purchase_item_payload([base_serials[1], base_serials[2], replacement, self.serials[9]], 225)
        validation = self.step(
            section,
            "validate removing sold serial is blocked",
            "SELECT validate_purchase_update2(%s,%s::jsonb)",
            [purchase_id, json.dumps(remove_sold_payload)],
        )
        data = json.loads(validation) if isinstance(validation, str) else validation
        self.assert_true(
            section,
            "sold serial removal validation is blocked",
            isinstance(data, dict) and data.get("is_valid") is False and sold in (data.get("sold_serials") or []),
            f"Expected sold serial {sold} blocked, got {data}",
        )
        self.step(
            section,
            "apply removing sold serial blocked",
            "SELECT update_purchase_invoice(%s,%s::jsonb,%s,%s,%s)",
            [purchase_id, json.dumps(remove_sold_payload), self.vendor, self.days[0], self.user_id],
            expect_error=True,
        )
        self.run_reports("after blocked sold serial removal")

        self.step(
            section,
            "purchase return updated replacement serial",
            "SELECT create_purchase_return(%s,%s::jsonb,%s)",
            [self.vendor, json.dumps([replacement]), self.user_id],
        )
        self.assert_stock(section, replacement, False)
        self.run_reports("after purchase return of replacement serial")

    def test_partial_returns_and_sale_mutation_guards(self):
        section = "03 partial returns and sale guards"
        vendor_id = self.party_id(self.vendor)
        customer_id = self.party_id(self.customer)
        serials = self.serials[10:14]

        self.step(
            section,
            "purchase four serials for partial return",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(self.purchase_item_payload(serials, 310)), self.user_id],
        )
        sale_id = self.step(
            section,
            "sell four serials in one invoice",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(self.sale_item_payload(serials, 410)), self.user_id],
        )
        for serial in serials:
            self.assert_stock(section, serial, False)
        self.run_reports("after four-serial sale")

        return_id = self.step(
            section,
            "partially return two of four serials",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps(serials[:2]), self.user_id],
        )
        for serial in serials[:2]:
            self.assert_stock(section, serial, True)
        for serial in serials[2:]:
            self.assert_stock(section, serial, False)
        self.run_reports("after partial sale return")

        self.step(
            section,
            "update sale invoice after return is blocked",
            "SELECT update_sale_invoice(%s,%s::jsonb,%s,%s,%s)",
            [sale_id, json.dumps(self.sale_item_payload(serials[2:], 430)), self.customer, self.days[2], self.user_id],
            expect_error=True,
        )
        self.assert_true(section, "sale invoice still exists after blocked update", self.sale_invoice_exists(sale_id))

        self.step(
            section,
            "delete sale invoice after return is blocked",
            "SELECT delete_sale(%s)",
            [sale_id],
            expect_error=True,
        )
        self.assert_true(section, "sale invoice still exists after blocked delete", self.sale_invoice_exists(sale_id))
        self.run_reports("after blocked sale update and delete")

        self.step(
            section,
            "update sale return from two serials to one returned serial",
            "SELECT update_sale_return(%s,%s::jsonb,%s)",
            [return_id, json.dumps([serials[0]]), self.user_id],
        )
        self.assert_stock(section, serials[0], True)
        self.assert_stock(section, serials[1], False)
        self.run_reports("after partial sale return update")

        self.step(
            section,
            "delete sale return restores returned serial to sold",
            "SELECT delete_sale_return(%s)",
            [return_id],
        )
        self.assert_true(section, "sale return deleted", not self.sale_return_exists(return_id))
        for serial in serials:
            self.assert_stock(section, serial, False)
        self.run_reports("after sale return delete")

    def test_sale_return_delete_update_after_resale(self):
        section = "04 sale return mutation after resale"
        vendor_id = self.party_id(self.vendor)
        customer_id = self.party_id(self.customer)
        cash_id = self.party_id("Cash Sale")
        serial = self.serials[14]
        replacement = self.serials[15]

        self.assert_true(section, "Cash Sale party exists", cash_id is not None)
        self.step(
            section,
            "purchase two serials for resale guard",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(self.purchase_item_payload([serial, replacement], 330)), self.user_id],
        )
        self.step(
            section,
            "credit sale serial before return",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(self.sale_item_payload([serial], 450)), self.user_id],
        )
        return_id = self.step(
            section,
            "credit sale return before resale",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([serial]), self.user_id],
        )
        self.assert_stock(section, serial, True)

        self.step(
            section,
            "cash resale after credit return",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [cash_id, self.days[2], json.dumps(self.sale_item_payload([serial], 500)), self.user_id],
        )
        self.assert_stock(section, serial, False)
        self.run_reports("after cash resale of returned serial")

        self.step(
            section,
            "delete old sale return after resale is blocked",
            "SELECT delete_sale_return(%s)",
            [return_id],
            expect_error=True,
        )
        self.assert_true(section, "old sale return still exists after blocked delete", self.sale_return_exists(return_id))

        self.step(
            section,
            "update old sale return after resale is blocked",
            "SELECT update_sale_return(%s,%s::jsonb,%s)",
            [return_id, json.dumps([serial]), self.user_id],
            expect_error=True,
        )
        self.assert_true(section, "old sale return still exists after blocked update", self.sale_return_exists(return_id))

        self.step(
            section,
            "wrong credit customer cannot return cash resale",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps([serial]), self.user_id],
            expect_error=True,
        )
        self.step(
            section,
            "cash customer can return cash resale",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            ["Cash Sale", json.dumps([serial]), self.user_id],
        )
        self.assert_stock(section, serial, True)
        self.run_reports("after cash sale return")

    def test_multi_item_mixed_serial_invoice(self):
        section = "05 multi-item mixed serial invoice"
        vendor_id = self.party_id(self.vendor)
        customer_id = self.party_id(self.customer)
        item_a_serials = self.serials[16:19]
        item_b_serials = self.serials[19:22]

        purchase_items = self.purchase_item_payload(item_a_serials, 120, self.item)
        purchase_items += self.purchase_item_payload(item_b_serials, 220, self.item_2)
        self.step(
            section,
            "purchase multi-item serial stock",
            "SELECT create_purchase(%s,%s,%s::jsonb,%s)",
            [vendor_id, self.days[0], json.dumps(purchase_items), self.user_id],
        )

        sale_items = self.sale_item_payload(item_a_serials, 180, self.item)
        sale_items += self.sale_item_payload(item_b_serials, 330, self.item_2)
        sale_id = self.step(
            section,
            "sell multi-item invoice with six serials",
            "SELECT create_sale(%s,%s,%s::jsonb,%s)",
            [customer_id, self.days[1], json.dumps(sale_items), self.user_id],
        )
        for serial in item_a_serials + item_b_serials:
            self.assert_stock(section, serial, False)
        self.run_reports("after multi-item sale")

        mixed_return = [item_a_serials[0], item_b_serials[0]]
        return_id = self.step(
            section,
            "return one serial from each item",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps(mixed_return), self.user_id],
        )
        for serial in mixed_return:
            self.assert_stock(section, serial, True)
        for serial in item_a_serials[1:] + item_b_serials[1:]:
            self.assert_stock(section, serial, False)
        self.run_reports("after multi-item partial return")

        self.step(
            section,
            "duplicate multi-item partial return is blocked",
            "SELECT create_sale_return(%s,%s::jsonb,%s)",
            [self.customer, json.dumps(mixed_return), self.user_id],
            expect_error=True,
        )

        self.step(
            section,
            "update multi-item return to different sold serials",
            "SELECT update_sale_return(%s,%s::jsonb,%s)",
            [return_id, json.dumps([item_a_serials[1], item_b_serials[1]]), self.user_id],
        )
        self.assert_stock(section, item_a_serials[0], False)
        self.assert_stock(section, item_b_serials[0], False)
        self.assert_stock(section, item_a_serials[1], True)
        self.assert_stock(section, item_b_serials[1], True)
        self.run_reports("after multi-item return update")

        self.step(
            section,
            "sale update after multi-item return is blocked",
            "SELECT update_sale_invoice(%s,%s::jsonb,%s,%s,%s)",
            [sale_id, json.dumps(sale_items), self.customer, self.days[2], self.user_id],
            expect_error=True,
        )
        self.step(
            section,
            "sale delete after multi-item return is blocked",
            "SELECT delete_sale(%s)",
            [sale_id],
            expect_error=True,
        )
        self.assert_true(section, "multi-item sale invoice still exists", self.sale_invoice_exists(sale_id))
        self.run_reports("after blocked multi-item sale mutation")

    def run(self):
        self.setup_master_data()
        self.test_purchase_sale_return_resale_purchase_return()
        self.test_mixed_purchase_update_corrections()
        self.test_partial_returns_and_sale_mutation_guards()
        self.test_sale_return_delete_update_after_resale()
        self.test_multi_item_mixed_serial_invoice()
        return self.results


def discover_tenants(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT c.schema_name, m.user_id
            FROM public.tenancy_company c
            JOIN public.tenancy_membership m ON m.company_id = c.id
            WHERE c.is_active = true AND c.schema_name IS NOT NULL
            ORDER BY c.id, m.user_id
            """
        )
        return cur.fetchall()
    finally:
        cur.close()


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    tenants = discover_tenants(conn)
    if not tenants:
        print("No active tenant memberships found.")
        return 2

    all_results: list[tuple[str, Result]] = []
    for schema, user_id in tenants:
        runner = DeepLifecycleRunner(conn, schema, user_id)
        results = runner.run()
        all_results.extend((schema, result) for result in results)

    by_schema: dict[str, list[Result]] = {}
    for schema, result in all_results:
        by_schema.setdefault(schema, []).append(result)

    print("\nFinancee deep transaction lifecycle results")
    print("=" * 80)
    for schema, results in by_schema.items():
        passed = sum(1 for r in results if r.ok)
        print(f"\n{schema}: {passed}/{len(results)} passed")
        current_section = None
        for result in results:
            if result.section != current_section:
                current_section = result.section
                print(f"  {current_section}")
            mark = "OK " if result.ok else "FAIL"
            suffix = f" - {result.detail}" if result.detail else ""
            print(f"    [{mark}] {result.name}{suffix}")

    failures = [(schema, r) for schema, r in all_results if not r.ok]
    print("\n" + "=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} deep lifecycle checks failed.")
        for schema, result in failures:
            print(f"- {schema} / {result.section} / {result.name}: {result.detail}")
        return 1

    print("PASSED: all deep lifecycle checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
