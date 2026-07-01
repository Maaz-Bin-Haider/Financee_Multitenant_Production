# Full-System Test Suite (`tests/suite/`)

A fresh, comprehensive test suite covering **every** functionality and **every**
report of the Financee system. It was written from a first-principles reading of
the live tenant schema (functions, triggers, chart of accounts) and the Django
routes — independent of the older ad-hoc scripts in `tests/`.

Each module runs against **every active tenant schema** and asserts on real
state, real money (trial balance, party balances, COGS), and real reports —
not just that a call "did not error".

## Running

Inside the `web` container (the whole suite):

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
```

A single domain:

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/suite/test_sales.py
docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web python tests/suite/test_http.py
```

`run_all.py` runs each module as its own process and prints a per-module
PASS/FAIL summary. Exit code is non-zero if any real check fails.

## Layout

| File | Covers |
|---|---|
| `_harness.py` | Shared harness: connection, per-tenant discovery, unique naming, business builders (party/item/purchase/sale/return/payment/receipt/contra), accounting assertions (trial balance, party balance, stock/serial state), and result recording (incl. `XFAIL`/`XPASS`). |
| `test_parties.py` | All party types, opening-balance accounting, expense-account creation, updates, lookups, balances. |
| `test_items.py` | Item create/update, lookups, stock-by-name, autocomplete. |
| `test_purchases.py` | Purchase create, Inventory/AP accounting, stock, fetch/navigation/summary, validated updates, delete guard. |
| `test_sales.py` | Credit + cash sales, AR/Revenue/COGS, updates, qty/serial guard, post-return mutation guards. |
| `test_returns.py` | Sale + purchase returns: create/update/delete, accounting reversal, stock restoration, every lifecycle guard. |
| `test_cash_movement.py` | Payments, receipts, contra: accounting, balances, navigation, history, guards. |
| `test_opening.py` | Opening cash (singleton), opening stock loads, Opening-Balance→Capital reclassification. |
| `test_owner_equity.py` | Capital injections/withdrawals, Cash/Capital effect, listing, deletion, guards. |
| `test_month_close.py` | Period preview / close / duplicate-close guard / listing / reverse (self-restoring). |
| `test_reports.py` | **Every** report: accounts, stock, serial, sales analytics, monthly, and all dashboard functions + views. |
| `test_http.py` | Real Django endpoints via the test client: pages render, JSON APIs return no 5xx, auth works, a master-data write flow succeeds. |

## Invariants asserted throughout

- **Double-entry**: trial balance (`SUM(debit) = SUM(credit)`) after every posting.
- **Party balances** move by the exact expected amount (AR/AP, payments, receipts).
- **COGS / revenue** match the underlying cost and price.
- **Stock/serial** state (`in_stock`, active `Sold`) stays coherent.
- **No empty journal entries** are ever left behind.

## `XFAIL` / `XPASS` and tenant drift

Confirmed-but-unfixed defects are marked as known bugs: reported as `XFAIL`
(documented) or `XPASS` (may now be fixed) and **excluded from the pass/fail exit
code**, so the suite stays green while tracking real issues.

This suite surfaced genuine **schema drift between tenants** (some idempotent
patches were applied to one tenant but not the other). Findings, all reproduced
by the suite:

1. **`create_purchase_return` missing in-stock guard on `tenant_company_1`.**
   A sold serial can be purchase-returned and a serial can be double-returned;
   `tenant_company_2` correctly blocks both. The return-serial-integrity patch
   was never applied to `tenant_company_1`. (`test_returns` XFAIL)
2. **Cash-party feature absent on `tenant_company_1`** (`is_cash` column and
   `get_cash_party_id` missing). The cash-sale path is only exercised where the
   feature exists. (`test_sales`)
3. **`item_history_view` missing on `tenant_company_2`** (present on
   `tenant_company_1`). (`test_reports` XFAIL)
4. **`item_transaction_history(text)` 1-arg overload is ambiguous on
   `tenant_company_1`** (a 3-arg-with-defaults variant collides). (`test_reports`)
5. **`get_item_names_like` is broken on PostgreSQL 16** (ambiguous `item_name`
   column) on both tenants. It is unused by the active item autocomplete view
   (which runs an inline query), so it is dead-but-broken. (`test_items` XFAIL)

Healing the drift = applying the existing idempotent patches under
`tenancy/sql/` to the lagging tenant (e.g. `fix_return_serial_integrity*.sql`),
after which the corresponding `XFAIL`s become `XPASS`.

## Notes

- Names are tagged per run and per process, so repeated runs never collide.
- Expected-failure and destructive-guard probes run inside a rolled-back
  transaction, so a wrongly-successful call never persists.
- The suite intentionally leaves its (valid, uniquely-named) accounting trail in
  place, exactly like the deep lifecycle test.
