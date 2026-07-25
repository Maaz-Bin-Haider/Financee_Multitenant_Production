#!/usr/bin/env python3
"""Phase 6 quantity accounting, journal, and numbering invariants."""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.db import DatabaseError, close_old_connections, connection, transaction  # noqa: E402

from tenancy.models import Company, Currency, INVENTORY_MODE_QUANTITY  # noqa: E402
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


def next_number(schema):
    close_old_connections()
    try:
        return q(schema, "SELECT quantity_next_document_number('sale')")[0][0]
    finally:
        close_old_connections()


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


def post_sql():
    return """
        SELECT quantity_post_journal(
            CURRENT_DATE, %s, %s, %s, %s, 1, %s::jsonb
        )
    """


def main():
    company = company_b = None
    try:
        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE6 ACCOUNTING {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE6 ACCOUNTING {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        required_version = schema_family(INVENTORY_MODE_QUANTITY).required_version

        chk("fresh schema reaches accounting version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0]
            == required_version)
        chk("fresh accounting schema verifies",
            verify_company_schema(company, use_cache=False).ok)

        expected = {
            "Cash", "Bank", "Accounts Receivable", "Input Tax", "Inventory",
            "Accounts Payable", "Output Tax", "Owner's Capital",
            "Opening Balance", "Retained Earnings", "Sales Revenue",
            "Cost of Goods Sold", "Inventory Adjustment Gain",
            "Inventory Adjustment Loss", "Exchange Gain", "Exchange Loss",
            "Rounding Difference",
        }
        accounts = q(schema, """
            SELECT account_name, account_type, normal_balance
              FROM chart_of_accounts ORDER BY account_code
        """)
        chk("required system accounts seeded",
            {row[0] for row in accounts} == expected, accounts)
        chk("system accounts seeded exactly once", len(accounts) == 17, len(accounts))
        chk("account normal balances match classifications", all(
            (typ in {"Asset", "Expense"} and normal == "Debit")
            or (typ in {"Liability", "Equity", "Revenue"} and normal == "Credit")
            for _name, typ, normal in accounts
        ))
        chk("account lookup searches names",
            ("1400",) in q(
                schema,
                "SELECT account_code FROM quantity_account_lookup('inventory')",
            ))
        chk("unknown account lookup is empty",
            q(schema, "SELECT * FROM quantity_account_lookup('not-an-account')") == [])

        lines = json.dumps([
            {"account_code": "1000", "debit": "1234.5678", "credit": "0"},
            {"account_code": "3000", "debit": "0", "credit": "1234.5678"},
        ])
        journal_id = q(
            schema, post_sql(),
            ["Capital injection", "owner_equity", 1, "CAP-000001", lines],
        )[0][0]
        totals = q(schema, """
            SELECT count(*), sum(debit), sum(credit)
              FROM journal_lines WHERE journal_id = %s
        """, [journal_id])[0]
        chk("balanced representative journal posts", journal_id > 0)
        chk("ledger preserves four-decimal base precision",
            totals[0] == 2 and totals[1] == totals[2]
            and str(totals[1]) == "1234.5678", totals)

        reversal_id = q(schema, """
            SELECT quantity_reverse_journal(%s, CURRENT_DATE, 'Undo test', 1)
        """, [journal_id])[0][0]
        chk("reversal creates a different journal", reversal_id != journal_id)
        links = q(schema, """
            SELECT o.status, o.reversal_journal_id, r.original_journal_id
              FROM journal_entries o
              JOIN journal_entries r ON r.journal_id = o.reversal_journal_id
             WHERE o.journal_id = %s
        """, [journal_id])[0]
        chk("reversal linkage is bidirectional",
            links == ("reversed", reversal_id, journal_id), links)
        reversed_lines = q(schema, """
            SELECT o.debit, o.credit, r.debit, r.credit
              FROM journal_lines o
              JOIN journal_lines r
                ON r.journal_id = %s AND r.account_id = o.account_id
             WHERE o.journal_id = %s ORDER BY o.line_id
        """, [reversal_id, journal_id])
        chk("reversal swaps debit and credit exactly",
            all(a == d and b == c for a, b, c, d in reversed_lines),
            reversed_lines)
        chk("second reversal is rejected", rejected(schema, """
            SELECT quantity_reverse_journal(%s, CURRENT_DATE, 'Again', 1)
        """, [journal_id]))
        chk("a reversal cannot itself be reversed", rejected(schema, """
            SELECT quantity_reverse_journal(%s, CURRENT_DATE, 'Again', 1)
        """, [reversal_id]))
        chk("posted journal header is immutable", rejected(schema, """
            UPDATE journal_entries SET description = 'tampered'
             WHERE journal_id = %s
        """, [journal_id]))
        chk("posted journal lines are immutable", rejected(schema, """
            UPDATE journal_lines SET debit = debit + 1
             WHERE journal_id = %s AND debit > 0
        """, [journal_id]))
        chk("posted journal cannot be deleted", rejected(
            schema, "DELETE FROM journal_entries WHERE journal_id = %s",
            [journal_id],
        ))
        chk("database rejects a directly inserted empty journal", rejected(
            schema, """
                INSERT INTO journal_entries (
                    entry_date, description, source_document_type
                ) VALUES (CURRENT_DATE, 'Direct empty', 'direct_test')
            """,
        ))
        chk("database rejects directly inserted unbalanced lines", rejected(
            schema, """
                WITH new_journal AS (
                    INSERT INTO journal_entries (
                        entry_date, description, source_document_type
                    ) VALUES (CURRENT_DATE, 'Direct unbalanced', 'direct_test')
                    RETURNING journal_id
                )
                INSERT INTO journal_lines (
                    journal_id, account_id, debit, credit
                )
                SELECT n.journal_id, a.account_id,
                       CASE WHEN a.account_code = '1000' THEN 10 ELSE 0 END,
                       CASE WHEN a.account_code = '3000' THEN 9 ELSE 0 END
                  FROM new_journal n
                  CROSS JOIN chart_of_accounts a
                 WHERE a.account_code IN ('1000', '3000')
            """,
        ))

        invalid = [
            ("empty", []),
            ("one-line", [{"account_code": "1000", "debit": 1}]),
            ("unbalanced", [
                {"account_code": "1000", "debit": 10},
                {"account_code": "3000", "credit": 9},
            ]),
            ("negative", [
                {"account_code": "1000", "debit": -10},
                {"account_code": "3000", "credit": -10},
            ]),
            ("both-sides", [
                {"account_code": "1000", "debit": 10, "credit": 1},
                {"account_code": "3000", "credit": 9},
            ]),
            ("zero-line", [
                {"account_code": "1000", "debit": 0, "credit": 0},
                {"account_code": "3000", "credit": 1},
            ]),
            ("unknown-account", [
                {"account_code": "DOES-NOT-EXIST", "debit": 1},
                {"account_code": "3000", "credit": 1},
            ]),
        ]
        for label, payload in invalid:
            chk(f"{label} journal rejected", rejected(
                schema, post_sql(),
                ["Invalid test", "test_invalid", None, None, json.dumps(payload)],
            ))

        before = q(schema, "SELECT count(*) FROM journal_entries")[0][0]
        chk("duplicate source document rejected", rejected(
            schema, post_sql(),
            ["Duplicate", "owner_equity", 1, "CAP-000001", lines],
        ))
        chk("rejected postings leave no partial journal",
            q(schema, "SELECT count(*) FROM journal_entries")[0][0] == before)

        trial = q(schema, """
            SELECT sum(total_debit), sum(total_credit), sum(balance)
              FROM quantity_trial_balance
        """)[0]
        chk("trial balance nets to zero",
            trial[0] == trial[1] and trial[2] == 0, trial)
        chk("post and reversal net every account to zero",
            q(schema, """
                SELECT count(*) FROM quantity_trial_balance WHERE balance <> 0
            """)[0][0] == 0)
        chk("stored journals are non-empty and balanced",
            q(schema, """
                SELECT count(*) FROM (
                    SELECT je.journal_id
                      FROM journal_entries je
                      LEFT JOIN journal_lines jl ON jl.journal_id = je.journal_id
                     GROUP BY je.journal_id
                    HAVING count(jl.line_id) < 2
                        OR sum(jl.debit) <> sum(jl.credit)
                        OR sum(jl.debit) <= 0
                ) invalid
            """)[0][0] == 0)

        numbers = [next_number(schema) for _ in range(3)]
        chk("document numbers use configured sequence",
            numbers == ["SAL-000001", "SAL-000002", "SAL-000003"], numbers)
        with ThreadPoolExecutor(max_workers=8) as pool:
            concurrent = list(pool.map(next_number, [schema] * 20))
        chk("concurrent document numbers are unique",
            len(set(concurrent)) == 20, concurrent)
        chk("successful concurrent numbering is gapless",
            sorted(int(value.split("-")[1]) for value in concurrent)
            == list(range(4, 24)), concurrent)
        chk("unknown document type rejected",
            rejected(schema, "SELECT quantity_next_document_number('unknown')"))
        chk("document-type counters are independent",
            q(schema, "SELECT quantity_next_document_number('purchase')")[0][0]
            == "PUR-000001")

        chk("second tenant has independent empty ledger",
            q(schema_b, "SELECT count(*) FROM journal_entries")[0][0] == 0)
        chk("second tenant has independent numbering",
            q(schema_b, "SELECT quantity_next_document_number('sale')")[0][0]
            == "SAL-000001")
        fingerprint_sql = """
            SELECT account_code, account_name, account_type, normal_balance
              FROM chart_of_accounts ORDER BY account_code
        """
        chk("tenant account fingerprints match",
            q(schema, fingerprint_sql) == q(schema_b, fingerprint_sql))
    finally:
        drop_company(company_b)
        drop_company(company)

    passed = sum(ok for _name, ok, _detail in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}"
              f"{' — ' + detail if detail and not ok else ''}")
    print(f"\nQuantity accounting: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
