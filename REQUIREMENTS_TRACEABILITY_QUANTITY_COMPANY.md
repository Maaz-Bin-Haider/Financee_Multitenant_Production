# Quantity Company Requirements Traceability Matrix

**Phase:** 2  
**SRS version:** 1.0  
**Architecture:** `ARCHITECTURE_QUANTITY_COMPANY.md`  
**Purpose:** Map every SRS requirement family to implementation phase,
component/SQL ownership, and mandatory test evidence.

Ranges in this matrix are inclusive. Every individual requirement ID inside a
listed range inherits the row’s implementation and evidence obligations.
Individual requirements that need a different owner are listed separately.

---

## 1. Functional Requirements

| SRS requirement IDs | Phase(s) | Application/component ownership | Tenant/public SQL ownership | Required evidence |
|---|---:|---|---|---|
| FR-COMP-001–005 | 3 | `tenancy.models`, admin form, provisioning service, schema-family registry | Public company migration/constraints | Company-type migration/admin/immutability tests; serial regression |
| FR-COMP-006–007 | 4 | Company admin and setup validation | Public currency catalogue/base currency/tax-mode migration | Currency seed/company creation/backfill tests |
| FR-TEN-001–008 | 5 | Registry, middleware, provisioning, family-aware management commands | Separate serial/quantity template, metadata, hardening, indexes | Fresh/rerun provisioning, mismatch denial, fingerprint, `search_path` tests |
| FR-ITEM-001–006 | 7 | Quantity item/variant capability, admin/views | `products`, `product_variants`, lookup functions | Variant combination, SKU, lock, lookup, isolation tests |
| FR-UOM-001–004 | 7 | Unit validation and UI | `units_of_measure`, quantity constraints | Whole/decimal boundary and immutability tests |
| FR-WH-001–004 | 8 | Warehouse views/permissions/context | `warehouses`, warehouse lookup/guard functions | CRUD/default/deactivate/reference/isolation tests |
| FR-WH-005–006 | 15 | Transfer capability/UI | Transfer headers/lines, FIFO lineage/movements | Transfer quantity/value/accounting/concurrency tests |
| FR-INV-001–008 | 9 | Quantity stock capability | Movements, balance projection, FIFO layers/allocations/reconciliation | FIFO, negative stock, lineage, replay, concurrency, reconciliation tests |
| FR-PUR-001–008 | 11 | Quantity purchase capability/views/UI | Purchase document functions, FIFO/journal posting | Full purchase lifecycle/accounting/backdating/idempotency tests |
| FR-SAL-001–009 | 12 | Quantity sale capability/views/UI | Sale document, availability, FIFO COGS functions | Sale lifecycle, oversell concurrency, accounting, duplicate tests |
| FR-SR-001–007 | 13 | Quantity sale-return capability | Return/source/allocation restoration functions | Partial/cumulative/concurrent/exact-cost lifecycle tests |
| FR-PR-001–006 | 14 | Quantity purchase-return capability | Source-lineage eligibility and return functions | Sold/transferred/prior-return/original-cost tests |
| FR-OPEN-001–002 | 10 | Quantity opening-stock capability | Opening document/layers/movements/journal | Opening quantity/value/reclassify/reversal tests |
| FR-COUNT-001–003 | 16 | Count workflow/approval UI | Count sessions/lines/post function | Snapshot, variance, approval, concurrent movement tests |
| FR-ADJ-001–004 | 16 | Adjustment workflow/permissions | Adjustment documents, FIFO and gain/loss journal | Positive/negative/approval/accounting/audit tests |
| FR-FIN-001–008 | 19 | Shared financial capabilities | Quantity-compatible party/payment/receipt/contra/equity/close SQL | Full finance parity, balance, close enforcement tests |
| FR-TAX-001–008 | 17 | Tax configuration and transaction payloads | Tax codes, line snapshots, calculation/journal functions | Inclusive/exclusive/classification/return/rounding matrix |
| FR-DISC-001–005 | 17 | Discount payload and UI | Line/invoice allocation calculation functions/columns | Percentage/fixed/line/invoice/order/history tests |
| FR-CUR-001–002 | 4 | Currency catalogue/company setup | Public currency catalogue and company base currency | Seed, selection, uniqueness, backfill, immutability tests |
| FR-CUR-003–010 | 18 | Foreign document/settlement capability | Foreign snapshots, payment/receipt allocations, realized FX functions | Rate rise/fall/same, partial settlement, report tests |
| FR-NUM-001–004 | 6 and document phases | Shared numbering service | Per-type PostgreSQL sequences/format functions | Concurrent uniqueness/no-reuse/format tests |
| FR-DATE-001–005 | 9, 11–19 | Mutation/replay service contracts | Close guard, dependency/replay functions | Backdated timeline, unsafe edit, closed-period, rollback tests |
| FR-ATT-001–004 | 20 | Attachment access/integration | Quantity document attachment metadata | Upload/replace/access/cleanup/cross-tenant tests |
| FR-UI-001–006 | 21 | Templates, JavaScript, Alerts, payload adapters | Authoritative SQL validation | Serial/quantity render, HTTP, duplicate-submit, responsive tests |
| FR-DASH-001–003 | 22 | Dashboard views/JavaScript | Quantity dashboard functions/views | KPI source reconciliation, rate-limit, HTTP tests |
| FR-SEC-001–002 | 20 | Central security mapping and view guards | Permission content types/migrations | Role/route/direct-call denial tests |
| FR-FEAT-001–002 | 20 | Family-aware feature catalogue/context/UI | Public company feature configuration | Unsupported/disabled UI and backend bypass tests |
| FR-SUB-001 | 20 | Existing subscription middleware/admin/email | Public subscription models unchanged | Active/grace/blocked/suspended parity tests |
| FR-AUD-001–002 | 20 | Audit service/admin/report | Append-only tenant/shared audit storage | Mutation coverage, user deactivation/history tests |

---

## 2. Report Requirements

| SRS requirement IDs | Phase | Application ownership | SQL/report ownership | Required evidence |
|---|---:|---|---|---|
| REP-ACC-001–008 | 22 | Accounts report catalogue/views/exports | Trial balance, ledgers, AR/AP, position, income, expense functions/views | Exact GL/party/source reconciliation and HTTP/export tests |
| REP-STK-001–013 | 22 | Stock report catalogue/views/exports | Movement, FIFO, valuation, aging, reorder, reconciliation, transfer/count views | Movement/FIFO/GL reconciliation, filters, performance tests |
| REP-SAL-001–011 | 22 | Sales report catalogue/views/exports | Daily/summary/product/customer/profit/margin/return functions | Source invoice/return/FIFO/revenue reconciliation |
| REP-PUR-001–005 | 22 | Purchase report catalogue/views/exports | Register/vendor/SKU/return/price-variance functions | Source purchase/return/cost reconciliation |
| Serial-only report exclusion table | 20–22 | Family report/feature catalogue and navigation | Route capability denial | Quantity hidden/direct denial plus serial availability tests |

---

## 3. Integration and Backend Requirements

| SRS requirement IDs | Phase | Ownership | Required evidence |
|---|---:|---|---|
| INT-API-001–002 | 21 | Schema-family registry/capability dispatch/payload adapters | Cross-mode hostile payload and trusted-family tests |
| INT-API-003–004 | 21 | Response contracts and validation | Contract, malformed input, precision, permissions tests |
| INT-API-005 | 6–21 | Stored transaction boundary and view orchestration | Failure rollback/no partial journal-stock tests |

---

## 4. Non-Functional Requirements

| SRS requirement IDs | Phase(s) | Ownership | Required evidence |
|---|---:|---|---|
| NFR-SEC-001–005 | 5, 20, 21, 25, 29 | Middleware, capability registry, permissions, attachments, error scrubber | Four-company concurrent leakage/security suite |
| NFR-DATA-001–005 | 6–19, 22 | PostgreSQL constraints/functions and fixed precision | Atomicity, constraint, historical snapshot, reconciliation tests |
| NFR-PERF-001–006 | 9, 22, 26 | SQL indexes/query plans, Gunicorn/PostgreSQL tuning | 100 sessions, 100k SKUs, 5m movements, report latency/resource evidence |
| NFR-OPS-001–004 | 27–30 | Deployment, backup, restore, health, compatibility | Restore, migration, rollback, ARM64 and production preflight evidence |
| NFR-MAIN-001–003 | 2–32 | Registry/capabilities/docs/test discipline | Architecture review, code review, documentation gate each phase |

---

## 5. Test Requirements

| SRS requirement IDs | Phase(s) | Planned location | Evidence |
|---|---:|---|---|
| TST-SER-001–002 | Every shared phase, 24 | Existing `tests/` and `tests/suite/` | Two-serial-tenant unchanged suite |
| TST-FLOW-001 | 23 | `tests/quantity/test_lifecycle_full.py` or equivalent | Full purchase/sale/return/transfer/count/FX/close flow |
| TST-CON-001–004 | 9, 12–16, 25 | Quantity concurrency harness | Oversell/return/transfer/edit/numbering concurrency |
| All Section 31 coverage bullets | 7–23 | Domain modules under quantity suite | Per-domain check totals and invariant evidence |
| Four-company matrix | 25 | Mixed-mode isolation harness | Zero leakage under concurrent reads/writes/errors/files |

---

## 6. CI/CD Requirements

| SRS requirement IDs | Phase | Ownership | Required evidence |
|---|---:|---|---|
| CICD-001 | 27 | Existing checks job | Compile/Django/migration gates |
| CICD-002–004 | 27 | CI bootstrap and schema validation jobs | Fresh four-company build and fingerprints |
| CICD-005–006 | 27 | Buildx/QEMU or native ARM runner | AMD64/ARM64 manifest and ARM smoke |
| CICD-007 | 27 | Production environment/approval | Approval gate preserved |
| CICD-008–010 | 27–31 | Family-aware deploy/preflight/postflight | Mismatch block, failed-tenant report, dual-family smoke |

---

## 7. Architecture-to-Test Artifacts

Planned test organization:

```text
tests/
  quantity/
    _harness.py
    test_provisioning.py
    test_accounting.py
    test_items_variants_units.py
    test_warehouses.py
    test_fifo.py
    test_opening.py
    test_purchases.py
    test_sales.py
    test_sale_returns.py
    test_purchase_returns.py
    test_transfers.py
    test_counts_adjustments.py
    test_tax_discounts.py
    test_currency.py
    test_shared_finance.py
    test_permissions_features_subscription.py
    test_attachments_audit.py
    test_http.py
    test_reports.py
    test_lifecycle_full.py
    test_concurrency.py
  mixed_mode/
    test_four_company_isolation.py
    test_concurrent_search_path.py
    test_cross_tenant_attachments.py
```

Exact filenames may change, but each matrix row must retain a test owner.

---

## 8. Traceability Gate

Before any implementation phase is marked complete:

1. List SRS IDs delivered by the phase.
2. Link code/SQL objects implementing them.
3. Link tests proving them.
4. Record exact results in the phase evidence.
5. Update this matrix if ownership changes.
6. Run the required serial regression evidence.

No SRS requirement is considered implemented because a table or endpoint merely
exists. Its accounting, security, concurrency, reconciliation, and failure
behavior must pass the mapped evidence.

