# Quantity-Based Company
## Complete Implementation and Rollout Plan

**Status:** Execution plan  
**Version:** 1.0  
**Date:** 2026-07-25  
**Requirements baseline:** `SRS_QUANTITY_BASED_COMPANY.md`  
**Execution checklist:** `todo.md`  
**Persistent architecture context:** `PROJECT_CONTEXT.md`

**Phase 2 architecture:** `ARCHITECTURE_QUANTITY_COMPANY.md`

**Requirements traceability:** `REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md`

---

## Execution Resume Checkpoint

- **Last completed:** Phase 26 — Performance and Capacity
- **Commit:** pending owner commit
- **Current phase:** Phase 27 — CI/CD and ARM64
- **Phase 27 status:** locally implemented and validated; clean PR and
  main-push GitHub-hosted T8 observations are pending.
- **Quantity schema development baseline:** version 22
- **Phase 26 status:** complete; the tuned 2-vCPU/4-GiB profile passed the full
  100k-SKU, five-million-movement, 100-session T7 gate.

**Phase 16 evidence:** `tests/PHASE16_QUANTITY_COUNTS_ADJUSTMENTS_RESULTS.md`.

**Phase 17 evidence:** `tests/PHASE17_QUANTITY_TAX_DISCOUNTS_RESULTS.md`.

**Phase 18 evidence:** `tests/PHASE18_QUANTITY_CURRENCY_RESULTS.md`.

**Phase 19 evidence:** `tests/PHASE19_QUANTITY_FINANCIAL_MODULES_RESULTS.md`.

**Phase 20 evidence:** `tests/PHASE20_QUANTITY_PLATFORM_CONTROLS_RESULTS.md`.

**Phase 21 evidence:** `tests/PHASE21_TYPE_AWARE_UI_RESULTS.md`.

**Phase 22 evidence:** `tests/PHASE22_QUANTITY_REPORTS_DASHBOARDS_RESULTS.md`.

**Phase 23 evidence:** `tests/PHASE23_COMPLETE_QUANTITY_SUITE_RESULTS.md`.

**Phase 24 evidence:** `tests/PHASE24_COMPLETE_SERIAL_REGRESSION_RESULTS.md`.

**Phase 25 evidence:** `tests/PHASE25_FOUR_COMPANY_ISOLATION_RESULTS.md`.

**Phase 26 evidence:** `tests/PHASE26_PERFORMANCE_CAPACITY_RESULTS.md`.

**Phase 27 evidence:** `tests/PHASE27_CICD_ARM64_RESULTS.md`.

Phase 18 is complete. Schema v14 includes immutable foreign/base snapshots,
partial and final cash/bank settlement allocations, realized exchange
gain/loss journals and reporting, return/settlement guards, and transaction
currency administration UI. No unrealized revaluation was introduced.

---

## 1. Purpose

This plan converts the approved quantity-company SRS into small,
independently verifiable implementation phases. The high number of phases is
intentional: each phase has a narrow scope, explicit artifacts, mandatory
tests, evidence, and an exit gate. A defect should be discovered close to the
change that introduced it instead of during final system integration.

This plan adds quantity companies without changing the behavior of current
serial companies. Existing paying companies remain serial-based throughout the
implementation and rollout.

---

## 2. Governing Documents

The four connected documents have different responsibilities:

| Document | Responsibility |
|---|---|
| `SRS_QUANTITY_BASED_COMPANY.md` | Defines what the system must do and the acceptance criteria. |
| `IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md` | Defines implementation order, phase gates, tests, evidence, rollout, and rollback. |
| `todo.md` | Tracks execution status and detailed actionable work. |
| `PROJECT_CONTEXT.md` | Preserves durable architecture, operational rules, and approved decisions for future development sessions. |

Conflict resolution:

1. Approved SRS requirements control product behavior.
2. This plan controls execution order and quality gates.
3. TODO status reflects work actually performed.
4. Project context records the architecture that actually exists.
5. A discovered conflict must be documented and approved; implementation shall
   not silently redefine an SRS requirement.

---

## 3. Mandatory Rules for Every Phase

Every implementation phase, including documentation and infrastructure phases,
shall follow this cycle:

1. Confirm the exact SRS requirement IDs in scope.
2. Record the phase as `IN PROGRESS` in `todo.md`.
3. Take a baseline of relevant existing tests.
4. Make only changes within the phase boundary.
5. Add or update tests in the same phase as the implementation.
6. Run the phase-specific tests.
7. Run the mandatory serial regression subset.
8. Run formatting, syntax, Django, migration, and SQL checks applicable to the
   phase.
9. Record commands, results, failures, and fixes.
10. Update documentation affected by the change.
11. Mark the phase complete only after its exit gate passes.

No phase may be declared complete based only on code review or compilation.
Real database behavior shall be tested for every phase that changes tenant SQL
or accounting.

If a phase fails:

- Stop dependent phases.
- Keep the failure reproducible.
- Identify whether the defect is requirements, design, implementation, test,
  data, environment, or deployment related.
- Fix it within the responsible phase where possible.
- Re-run the complete phase gate, not only the previously failing assertion.
- Record important diagnosed defects in `FIXED_ISSUES.md`.

---

## 4. Test Levels

The following test levels are referenced by phase gates:

| Level | Test type |
|---|---|
| `T0` | Formatting, static inspection, SQL parsing/build checks, Python compilation. |
| `T1` | Unit/contract tests for a narrow component. |
| `T2` | Quantity tenant integration tests against real PostgreSQL. |
| `T3` | Existing serial regression subset relevant to the changed shared code. |
| `T4` | Complete serial test suite against two serial tenants. |
| `T5` | Complete quantity test suite against two quantity tenants. |
| `T6` | Four-company concurrent multitenancy/isolation suite. |
| `T7` | Performance, load, resource, and long-running reliability tests. |
| `T8` | Deployment, backup, restore, migration, rollback, ARM64, and staging tests. |
| `T9` | Production-safe smoke tests and post-release monitoring. |

Every phase below names its minimum levels. Additional tests shall be added
when risk or discoveries require them.

---

## 5. Environments

### 5.1 Development

- Local or isolated Docker stack.
- Synthetic data only.
- May be reset frequently.
- At least one serial and one quantity tenant once provisioning exists.

### 5.2 Integration

- Isolated Docker environment.
- Exactly four principal tenants:
  - Serial Company A.
  - Serial Company B.
  - Quantity Company A.
  - Quantity Company B.
- Used for full regression, concurrency, leakage, and realistic lifecycle
  testing.

### 5.3 Staging

- No connection to production database or media.
- Same image, ARM64 architecture where possible, environment layout, Nginx,
  Redis, PostgreSQL version, and deployment flow as production.
- Uses sanitized restored data plus synthetic quantity tenants.

### 5.4 Production

- Current three companies remain serial-based.
- Quantity pilot is created only after the production serial verification gate.
- No destructive test data is posted to existing customer tenants.

---

## 6. Phase Overview

| Phase | Name | Primary gate |
|---:|---|---|
| 0 | Requirements baseline | SRS approved |
| 1 | Baseline capture and test stabilization | Current serial suite green |
| 2 | Architecture and schema-family design | Design review |
| 3 | Public company metadata migration | Existing companies remain serial |
| 4 | Currency catalogue and company setup | Company setup contracts green |
| 5 | Quantity schema foundation | Fresh/rerun schema builds |
| 6 | Chart of accounts and journal foundation | Double-entry harness green |
| 7 | Product, variants, SKU, and units | Master-data suite green |
| 8 | Warehouses and warehouse security | Warehouse suite green |
| 9 | Stock movement and FIFO engine | FIFO invariant suite green |
| 10 | Opening stock | Opening suite green |
| 11 | Quantity purchases | Purchase suite green |
| 12 | Quantity sales | Sale/concurrency suite green |
| 13 | Sale returns | Sale-return suite green |
| 14 | Purchase returns | Purchase-return suite green |
| 15 | Warehouse transfers | Transfer suite green |
| 16 | Counts and adjustments | Count/reconciliation suite green |
| 17 | Tax and discount engine | Calculation/accounting suite green |
| 18 | Multi-currency settlement | Currency suite green |
| 19 | Shared financial modules and month close | Full financial parity green |
| 20 | Attachments, descriptions, audit, permissions, features | Security suite green |
| 21 | Quantity UI and type-aware backend | HTTP/browser contract suite green |
| 22 | Quantity reports and dashboards | Report reconciliation green |
| 23 | Complete quantity suite | Two quantity tenants green |
| 24 | Complete serial regression | Two serial tenants green |
| 25 | Four-company isolation and concurrency | Zero leakage |
| 26 | Performance and capacity | Targets measured/approved |
| 27 | CI/CD and ARM64 | Pipeline green |
| 28 | Backup, restore, migration, and rollback rehearsal | Recovery proof |
| 29 | Staging acceptance and security review | Release candidate approved |
| 30 | Controlled production foundation deployment | Existing tenants verified |
| 31 | Quantity pilot provisioning | Pilot reconciliation green |
| 32 | Observation, support, and general availability | Stability approval |

Phase 0 is complete. Phases 1–32 are implementation and rollout work.

---

## Phase 0 — Requirements Baseline

### Scope

- Approve quantity behavior, FIFO, units, warehouses, variants, SKU, taxes,
  discounts, currency, reports, scale, and rollout.
- Produce the SRS and this implementation plan.

### Deliverables

- `SRS_QUANTITY_BASED_COMPANY.md`.
- Phase 0 decisions in `PROJECT_CONTEXT.md`.
- Execution roadmap in `todo.md`.
- This implementation and rollout plan.

### Tests and review

- `T0`: Markdown formatting and internal consistency.
- Verify every owner-approved decision appears in the SRS decisions register.
- Verify SRS differentiates serial parity from quantity-new requirements.

### Exit gate

- Product decisions approved.
- No unresolved Phase 0 owner decision.
- Phase 1 may start.

---

## Phase 1 — Baseline Capture and Test Stabilization

### Objectives

Establish trustworthy evidence of current serial behavior before shared code or
public models change.

### Work

- Record current commit SHA, dependencies, Docker versions, schema versions,
  tenant inventory, and test commands.
- Run the full existing serial suite from a clean reset.
- Capture check totals, duration, resource usage, and any flaky behavior.
- Verify current production image builds for AMD64 and ARM64.
- Inventory all current routes, permissions, feature flags, SQL functions,
  tables, views, triggers, and report endpoints.
- Create a machine-readable serial behavior manifest where practical.
- Confirm the worktree contains no unrelated modifications before implementation
  commits are prepared.

### Mandatory tests

- `T0`: compileall, Django check, migration check, shell/compose validation.
- `T4`: all current tests against two fresh serial tenants.
- Existing deep lifecycle and HTTP harnesses.
- Fresh serial provisioning and repeated serial hardening.

### Evidence

- Baseline results file with timestamp and commit SHA.
- Failures documented before new feature work.

### Exit gate

- All real serial checks pass or every pre-existing failure is explicitly
  documented and approved.
- No implementation proceeds on an unreliable baseline.

---

## Phase 2 — Architecture and Schema-Family Design

### Objectives

Define the solution before physical SQL and shared backend changes.

### Work

- Design schema-family registry/capability layer.
- Design public company fields and immutability.
- Design quantity schema names, versioning, hardening, patch, and provisioning
  workflow.
- Produce logical entity relationship diagrams.
- Define function naming and API payload contracts.
- Define document lifecycle/state and reversal rules.
- Define FIFO allocation and rebuild algorithms.
- Define lock order to avoid overselling and deadlocks.
- Define money, quantity, tax, discount, and rate precision/rounding.
- Define report-to-source reconciliation rules.
- Map every SRS requirement to planned modules, SQL objects, and tests.
- Review compatibility with rollback to the current application image.

### Mandatory tests/reviews

- `T0`: document lint/format checks.
- Architecture threat review for tenant/type confusion.
- Walk through purchase → transfer → sale → return → edit → close.
- Walk through foreign purchase → partial payments at changing rates.
- Review deadlock and transaction boundaries.

### Exit gate

- Approved logical model and capability dispatch.
- No mixed serial/quantity business table design.
- Every P0 SRS requirement has an implementation and test owner/location.

---

## Phase 3 — Public Company Metadata Migration

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE3_COMPANY_METADATA_RESULTS.md`.

### Objectives

Introduce company type safely without changing existing tenant behavior.

### Work

- Add company type, base currency reference, and tax-mode fields as designed.
- Backfill every existing company as serial.
- Enforce immutable type after provisioning.
- Update admin form and confirmation.
- Add audit evidence for company creation/type.
- Do not enable quantity provisioning yet.

Implementation note: this phase delivered the inventory-mode migration and
gate. The worldwide currency catalogue, base-currency selection, and
tax/non-tax company setup remain grouped in Phase 4 so their reference data,
backfill policy, immutability rules, and tests land atomically.

### Mandatory tests

- `T0`: Django checks and missing-migration guard.
- `T1`: model/admin validation and migration tests.
- `T3`: authentication, membership, admin, subscription, and feature tests.
- Migration forward/backward compatibility rehearsal on a database copy.
- Verify all existing companies remain serial with unchanged schema names.

### Exit gate

- Existing-company behavior and serial provisioning are unchanged.
- Type cannot be changed after provisioning.
- Quantity selection remains safely unavailable until its template exists.

---

## Phase 4 — Currency Catalogue and Company Setup

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE4_COMPANY_SETUP_RESULTS.md`.

### Objectives

Provide stable shared reference data needed before quantity schemas are
provisioned.

### Work

- Add worldwide ISO currency catalogue.
- Seed currency codes, names, symbols, and monetary precision idempotently.
- Add base-currency selection to company creation.
- Enforce base-currency immutability after financial activity.
- Add tax/non-tax selection.
- Define a safe default/backfill for existing serial companies without changing
  serial accounting.

### Mandatory tests

- `T1`: catalogue uniqueness, idempotent seed, admin selection.
- `T3`: serial company creation and existing admin workflows.
- Migration tests with existing companies and memberships.
- Verify no currency symbol or precision changes existing stored serial values.

### Exit gate

- Company setup data is stable and backward compatible.
- No existing customer requires manual repair.

---

## Phase 5 — Quantity Schema Foundation

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE5_QUANTITY_FOUNDATION_RESULTS.md`.

### Objectives

Create the independently provisionable quantity schema skeleton.

### Work

- Create quantity template and hardening files.
- Add schema metadata and version.
- Add quantity-family provisioning dispatch.
- Create base tables, sequences, constraints, ownership, and seed framework.
- Add quantity-only management commands/options.
- Add schema-family verification during activation.

### Mandatory tests

- `T0`: SQL file checks.
- `T2`: provision empty quantity schema from scratch.
- Rerun quantity hardening multiple times.
- Provision two quantity tenants and compare object fingerprints.
- Intentionally mismatch public type/schema type and verify safe denial.
- `T3`: fresh serial provisioning and existing serial hardening.

### Exit gate

- Fresh and repeated quantity provisioning is deterministic.
- Serial and quantity artifacts cannot be applied to the wrong family.

---

## Phase 6 — Accounting and Journal Foundation

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE6_ACCOUNTING_FOUNDATION_RESULTS.md`.

### Objectives

Establish the quantity schema’s chart of accounts and double-entry primitives.

### Work

- Define base chart of accounts.
- Add journal headers/lines and constraints.
- Add account lookup and trial-balance views/functions.
- Add cash, AR, AP, Inventory, Revenue, COGS, Opening Balance, Capital,
  adjustment gain/loss, tax, and exchange gain/loss accounts.
- Prevent empty/unbalanced posting.

### Mandatory tests

- `T2`: seed accounts exactly once.
- Post/reverse representative balanced journals.
- Reject unbalanced, empty, negative-invalid, and unknown-account entries.
- Trial balance must net to zero.
- `T3`: serial trial balance and core transaction subset.

### Exit gate

- Accounting primitives are reliable before inventory modules use them.

---

## Phase 7 — Product, Variant, SKU, and Unit Masters

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE7_ITEM_MASTER_RESULTS.md`.

### Objectives

Implement quantity sellable-item identity.

### Work

- Item/product master.
- Variant dimensions: brand, model, color, storage, RAM, region, condition.
- Unique SKU suggestion and manual override.
- Lock SKU and unit after transactions.
- Units: Piece, Box, Kilogram, Gram, Litre, Metre.
- Whole-number enforcement for Piece/Box.
- Three-decimal support for measurement units.
- Lookup, autocomplete, list, update, active/inactive behavior.

### Mandatory tests

- `T1/T2`: every dimension and combination.
- Duplicate SKU and duplicate normalized combination rejection.
- Suggested SKU collision handling.
- Manual SKU before transaction; blocked mutation afterward.
- Unit precision boundary tests.
- Invalid fractional Pieces/Boxes rejected in database and HTTP layer.
- `T3`: existing serial item suite.

### Exit gate

- One unambiguous SKU identifies every sellable quantity variant.

---

## Phase 8 — Warehouse Foundation

**Status:** Completed 2026-07-25. Evidence:
`tests/PHASE8_WAREHOUSE_RESULTS.md`.

### Objectives

Implement warehouse identity and permissions before stock exists.

### Work

- Warehouse master and default warehouse.
- Active/inactive rules.
- Warehouse permissions.
- Warehouse-aware lookup contracts.
- Block deletion of referenced warehouses.

### Mandatory tests

- `T1/T2`: create, rename, deactivate, default selection, duplicate checks.
- Unauthorized warehouse mutation denied.
- Referenced warehouse deletion blocked.
- Tenant isolation between same-named warehouses.
- `T3`: shared admin/permission regression.

### Exit gate

- Warehouse master is safe for inventory references.

---

## Phase 9 — Stock Movement and FIFO Engine

**Status:** completed 2026-07-25. Quantity schema version 5 and all mandatory
acceptance tests passed in the isolated mixed-family Docker environment. See
`tests/PHASE9_FIFO_ENGINE_RESULTS.md`. Phase 10 is the next authorized phase;
no invoice UI was enabled by this phase.

### Objectives

Build and prove the inventory core independently of full invoices.

### Work

- Stock movement ledger.
- FIFO layers and remaining quantity.
- FIFO consumption allocations.
- Availability function per SKU/warehouse/date.
- Row-lock order and transaction boundaries.
- Rebuild/replay mechanism for permitted backdating and edits.
- Stock/FIFO/inventory reconciliation functions.

### Mandatory tests

- `T2`: single and multiple cost layers.
- Partial and full consumption.
- Same SKU across warehouses.
- Backdated layer insertion and replay.
- Historical negative-stock rejection.
- Concurrent consumption near zero stock.
- Deadlock/retry tests.
- Movement quantity equals FIFO remainder.
- No invoice UI is integrated until these pass.
- `T3`: serial inventory lifecycle subset.

### Exit gate

- FIFO results are deterministic, concurrent-safe, and reconcilable.

---

## Phase 10 — Opening Stock

**Status:** completed 2026-07-25. Quantity schema version 6, the guarded
quantity opening-stock UI/API, and all mandatory acceptance tests passed in the
isolated mixed-family Docker environment. See
`tests/PHASE10_OPENING_STOCK_RESULTS.md`. Phase 11 is the next authorized
phase.

### Objectives

Add quantity opening inventory and existing accounting reclassification.

### Work

- Opening stock document and numbering.
- Warehouse/SKU/quantity/unit cost posting.
- Opening FIFO layers and movements.
- Opening Balance accounting.
- Guarded details, list, delete/reversal.
- Reclassification to Capital.

### Mandatory tests

- `T2`: whole and decimal units, multiple SKUs/warehouses, duplicate/invalid
  inputs, reversal, reclassification.
- Exact movement, FIFO, Inventory, Opening Balance, and Capital assertions.
- `T3`: current serial opening-stock and opening-cash tests.

### Exit gate

- Opening stock reconciles at quantity and value levels.

---

## Phase 11 — Quantity Purchases

**Status:** completed 2026-07-25. Quantity schema version 7 and the domestic
base-currency credit/cash purchase lifecycle passed all focused and regression
gates in the isolated mixed-family Docker environment. See
`tests/PHASE11_QUANTITY_PURCHASES_RESULTS.md`. Tax, foreign currency,
attachments, and the shared party master remain in their assigned later
phases. Phase 12 is next.

### Objectives

Implement domestic base-currency purchases before tax and foreign complexity.

### Work

- Purchase headers/lines and sequence.
- Vendor/warehouse/SKU/quantity/unit cost/description.
- FIFO layer and movement creation.
- Credit and cash accounting.
- Fetch/navigation/summary.
- Guarded edit and reversal/delete.
- Attachments may remain stubbed until their dedicated phase.

### Mandatory tests

- `T2`: multi-line/multi-SKU, multiple costs, cash/credit, invalid quantity,
  invalid unit precision, edit, reversal, duplicate submit, navigation.
- Backdated purchase with later consumption.
- Concurrent purchase and sale interaction at SQL level.
- Inventory/AP/Cash/trial-balance/FIFO assertions after every mutation.
- `T3`: complete existing serial purchase suite.

### Exit gate

- Domestic pre-tax purchase lifecycle is fully reconciled.

---

## Phase 12 — Quantity Sales

### Objectives

Implement domestic base-currency sales with FIFO COGS.

### Work

- Sale headers/lines and sequence.
- Warehouse availability and atomic lock.
- Credit/cash revenue posting.
- FIFO allocation and COGS.
- Fetch/navigation/summary.
- Guarded edit and reversal/delete.
- Duplicate-submit protection.

### Mandatory tests

- `T2`: exact-stock, partial-stock, multiple layers, multiple warehouses,
  cash/credit, multi-line, editing price/quantity/date/warehouse.
- Zero/negative/excessive/fractionally invalid quantities.
- Concurrent final-stock sales; exactly one permissible outcome.
- Revenue, AR/Cash, COGS, Inventory, FIFO, and trial balance assertions.
- `T3`: complete existing serial sale suite.

### Exit gate

- No oversell and exact FIFO accounting under concurrency.

---

## Phase 13 — Quantity Sale Returns

### Objectives

Implement partial returns with exact historical cost restoration.

### Work

- Return header/lines and sequence.
- Original sale-line linkage.
- Remaining returnable quantity.
- Exact FIFO allocation reversal.
- Warehouse restoration.
- Cash/credit revenue and tax-ready accounting structure.
- Guarded update and reversal/delete.

### Mandatory tests

- `T2`: partial, repeated partial, full, multiple lines, wrong customer,
  excessive cumulative return, returned stock resale, update/delete.
- Concurrent returns against the remaining quantity.
- Exact original COGS restoration after multiple purchase-cost layers.
- Sale edit/delete interaction.
- `T3`: complete existing serial sale-return suite and lifecycle guards.

### Exit gate

- Return quantities and restored costs exactly match source allocations.

---

## Phase 14 — Quantity Purchase Returns

### Objectives

Implement original-cost purchase returns with eligibility guards.

### Work

- Return header/lines and sequence.
- Original purchase-line linkage.
- Eligible source quantity calculation.
- Original purchase cost.
- Credit/cash reversal.
- Guarded update and reversal/delete.

### Mandatory tests

- `T2`: partial/full/repeated returns, wrong vendor, sold quantity, transferred
  quantity, double return, update/delete, backdated return.
- Concurrent return and sale.
- Exact AP/Cash/Inventory/FIFO assertions.
- `T3`: complete existing serial purchase-return suite.

### Exit gate

- No unavailable or already-consumed purchase quantity can be returned.

---

## Phase 15 — Warehouse Transfers

### Objectives

Move FIFO quantities between warehouses without changing company value.

### Work

- Transfer headers/lines and numbering.
- Source consumption and destination layer creation/preservation.
- Description and audit hooks.
- Guarded correction/reversal.

### Mandatory tests

- `T2`: full/partial/multi-layer/multi-SKU transfers.
- Same warehouse, unavailable stock, inactive warehouse, concurrent
  sale/transfer, backdated transfer.
- Total company quantity/value unchanged.
- Source/destination movement reconciliation.
- No revenue/expense/AR/AP effect.
- `T3`: shared permission and report regression.

### Exit gate

- Warehouse quantities change atomically while company inventory value remains
  unchanged.

---

## Phase 16 — Physical Counts and Adjustments

### Objectives

Provide controlled reconciliation between physical and system stock.

### Work

- Count session/lines and sequence.
- Count cutoff/snapshot behavior.
- Variance calculation.
- Approval workflow.
- Positive/negative adjustments, reasons, permissions, and journal accounts.
- FIFO valuation for adjustments.
- Audit trail and reversal policy.

### Mandatory tests

- `T2`: exact count/no adjustment, shortage, surplus, multiple warehouses,
  concurrent movement during count, approval permissions, repeated posting,
  reversal.
- Negative count/adjustment guards.
- Inventory and adjustment gain/loss accounting.
- Integrity report becomes clean after valid posting.
- `T3`: owner-equity/month-close/accounting subset.

### Exit gate

- Counts are reproducible and adjustments are authorized, balanced, and
  auditable.

---

## Phase 17 — Tax and Discount Engine

### Objectives

Add approved pricing calculations to purchases, sales, and returns.

### Work

- Tax/non-tax company behavior.
- Tenant tax-code administration.
- Taxable, zero-rated, exempt classifications and references.
- Inclusive/exclusive mode and defaults.
- Percentage/fixed line and invoice discounts.
- Proportional invoice-discount allocation.
- Tax control accounts and return reversal.
- Historical calculation snapshots.

### Mandatory tests

- `T1/T2`: calculation matrices across quantity, price, discounts, tax rates,
  inclusive/exclusive, exemptions, rounding, partial returns.
- Non-tax company cannot accidentally post tax.
- Tax configuration changes do not alter history.
- 0%, 100%, excessive, negative, and rounding-edge tests.
- Journal tax-control balances reconcile to invoice tax reports.
- `T3`: complete serial transaction suite to prove shared changes do not alter
  current serial totals.

### Exit gate

- Independently calculated invoice and journal totals match for every matrix
  case.

---

## Phase 18 — Multi-Currency and Realized Gain/Loss

**Status: COMPLETE — 2026-07-26**

### Objectives

Implement foreign invoices and settlement without unrealized revaluation.

### Work

- Transaction currency and foreign amounts.
- Manual invoice exchange rate.
- Permanent base-value snapshot.
- Payment/receipt allocation to foreign invoices.
- Manual settlement rate.
- Partial settlement and remaining foreign balance.
- Realized exchange gain/loss accounts and reporting.
- Explicit exclusion of month-end unrealized revaluation.

### Mandatory tests

- `T2`: foreign purchase/sale, rate rise/fall/same, partial/multiple
  settlements, overpayment guard, returns before/after settlement, cash/bank and
  party reconciliation.
- Domestic invoice never asks for/runs rate conversion.
- Zero/negative/missing rate rejected.
- Historical invoice values remain unchanged.
- Realized gain/loss included in profit/expense reports.
- `T3`: serial payments/receipts/contra and transaction suites.

### Exit gate

- Foreign party balance, base ledger, cash/bank, and realized gain/loss all
  reconcile after partial and full settlement.

Completion evidence: focused Phase 18 integration passed 23/23; all 31
mixed-family modules, HTTP 70/70, system 111/111, and deep serial lifecycle
2702/2702 passed. See `tests/PHASE18_QUANTITY_CURRENCY_RESULTS.md`.

---

## Phase 19 — Shared Financial Modules and Month Close

**Status: COMPLETE — 2026-07-26**

### Objectives

Complete quantity compatibility for non-inventory financial modules.

### Work

- Parties and opening balances.
- Payments, receipts, and contra.
- Opening cash.
- Owner equity.
- Month close preview/close/reversal.
- Closed-period enforcement on every quantity mutation.

### Mandatory tests

- `T2`: full quantity-company financial module suite.
- Closed-period attempts for purchase, sale, both returns, transfer, count,
  adjustment, payment, receipt, contra, opening, and edit/delete.
- Trial balance and party/cash balances after each.
- `T3`: complete corresponding serial suites.

### Exit gate

- Shared financial behavior has accounting parity and universal close guards.

Completion evidence: focused Phase 19 integration passed 27/27; all 32
mixed-family modules, HTTP 70/70, system 111/111, focused opening stock 37/37,
and deep serial lifecycle 2702/2702 passed. See
`tests/PHASE19_QUANTITY_FINANCIAL_MODULES_RESULTS.md`.

---

## Phase 20 — Attachments, Descriptions, Audit, Permissions, and Features

### Objectives

Integrate shared platform controls and new quantity capabilities.

### Work

- Attachment metadata/access/cleanup for all quantity documents.
- Descriptions and smart-description behavior.
- Immutable audit events.
- New permissions and migrations.
- Feature catalogue by company type.
- Backend and UI enforcement.
- Subscription behavior for quantity tenants.

### Mandatory tests

- `T1/T2`: upload, replace, preview, download, cleanup, invalid files,
  unauthorized/cross-tenant access, feature-disabled access.
- Audit completeness for every mutation.
- Permission matrix for all roles/routes.
- Subscription active/grace/blocked/suspended behavior.
- Direct URL/API bypass attempts.
- `T3`: complete serial attachment, feature, subscription, and permission
  suites.

### Exit gate

- Shared controls work identically and no quantity route bypasses them.

---

## Phase 21 — Type-Aware Backend and Quantity UI

### Objectives

Connect the proven SQL modules to Django and the browser without mixing modes.

### Work

- Central schema-family capability dispatch.
- Quantity payload parsing/validation.
- Mode-aware routes/views/templates/JavaScript.
- Company type visible in admin/context where useful.
- Quantity forms for purchase, sale, returns, warehouse, count, and adjustment.
- Existing theme and `Alerts` integration.
- Loading/duplicate-submit behavior.
- Responsive and keyboard workflows.

### Mandatory tests

- `T1/T2`: request/response contracts and real Django client writes.
- Serial payload rejected in quantity mode and inverse bypass rejected.
- Page render and JSON API tests for both types.
- Browser-level calculation previews compared with authoritative SQL results.
- Mobile/responsive and accessibility review.
- `T3`: complete serial HTTP suite.

### Exit gate

- Users see only controls valid for their company type, and the backend
  independently enforces the same rule.

---

## Phase 22 — Quantity Reports and Dashboards

### Objectives

Implement every SRS report and remove only unsupported quantity navigation.

### Work

- Accounts reports.
- Stock/movement/FIFO/warehouse/count/reconciliation reports.
- Sales/profit/margin/return reports.
- Purchase/vendor/price-variance reports.
- Expense and month-end profit reports.
- Quantity dashboards.
- CSV/Excel exports.
- Central report availability catalogue.
- Quantity replacements for serial-only reports.

### Mandatory tests

- `T2`: every report function, view, endpoint, filter, export, permission, and
  feature flag.
- Reconcile totals to independently calculated source and journal values.
- Unsupported serial endpoints hidden and backend-blocked for quantity tenants.
- Serial-only reports remain functional for serial tenants.
- Date, warehouse, SKU, variant, customer, vendor, tax, and currency filters.
- `T3`: complete existing serial reports/dashboard suite.

### Exit gate

- Every supported report reconciles; no serial-only report is accidentally
  removed or exposed to quantity tenants.

---

## Phase 23 — Complete Quantity Suite

### Objectives

Validate the entire quantity system on two independent quantity tenants.

### Work and tests

- `T5`: run every quantity module against Quantity Company A and B.
- Run full real-life lifecycle.
- Run hostile/invalid input suite.
- Run fresh provisioning and repeated hardening.
- Run schema upgrade from every released quantity version.
- Verify all SRS P0/P1 requirements have test evidence.

### Exit gate

- Zero unexplained real failures.
- Zero XFAIL for release-blocking behavior.
- Both quantity schemas have identical required object fingerprints.

---

## Phase 24 — Complete Serial Regression

### Objectives

Prove the new feature did not disturb the existing product.

### Work and tests

- `T4`: all existing tests on two serial tenants.
- Compare key totals and response contracts to Phase 1 baseline.
- Provision a fresh serial tenant.
- Rerun serial hardening.
- Confirm no quantity controls, tables, or reports appear in serial workflows
  unless deliberately shared.

### Exit gate

- Existing serial behavior remains green and compatible.
- Any intentional shared change is documented and approved.

---

## Phase 25 — Four-Company Isolation and Concurrency

### Objectives

Prove multitenancy under simultaneous mixed-mode activity.

### Work and tests

- `T6`: two serial plus two quantity tenants.
- Concurrent purchases, sales, returns, transfers, counts, reports, exports,
  attachments, exceptions, and logouts.
- Persistent database connections and Gunicorn threads.
- Cache/rate-limit key isolation.
- Cross-tenant guessed IDs and attachment paths.
- Schema mismatch and exception reset tests.
- Verify `search_path` returns to `public`.

### Exit gate

- Zero cross-tenant data, file, report, error, cache, or connection leakage.

---

## Phase 26 — Performance and Capacity

### Objectives

Measure production capacity rather than assume it.

### Work and tests

- `T7`: 100 concurrent sessions.
- 100,000 SKUs.
- Five million stock movements.
- Approximately 100,000 physical units across warehouses.
- Representative 100 invoices/day plus 30–40 other transactions/day.
- Normal reports under three seconds.
- Heavy export behavior.
- Backdated FIFO rebuild worst cases.
- Monitor CPU credits, RAM, swap, disk I/O, connections, locks, query plans, and
  container restarts.
- Tune PostgreSQL/Gunicorn for 2 vCPU/4 GiB or document required EC2 resize.

### Exit gate

- Targets pass, or an approved infrastructure upgrade is documented and tested.

---

## Phase 27 — CI/CD and ARM64

### Objectives

Make all quality gates repeatable in automation.

### Work

- Add four-company CI bootstrap.
- Separate serial/quantity/full-isolation stages.
- Add schema family/version/fingerprint checks.
- Add ARM64 smoke execution.
- Publish signed/pinned multi-architecture images if adopted.
- Add preflight and post-deploy family-aware checks.
- Preserve approval-gated production deployment.

### Mandatory tests

- `T8`: run workflow from a clean branch/PR and main-equivalent build.
- Verify failure artifacts and exact failing tenant/module.
- Verify both image architectures.
- Simulate failed health check and image rollback.

### Exit gate

- CI cannot publish/deploy when any mandatory serial, quantity, isolation, or
  ARM64 gate fails.

---

## Phase 28 — Backup, Restore, Migration, and Rollback Rehearsal

### Objectives

Prove recoverability before staging approval.

### Work and tests

- `T8`: encrypted off-server database and media backup.
- Restore into an isolated environment.
- Verify every restored serial tenant.
- Apply public company-type migration and schema-family-aware deployment.
- Provision quantity tenants after restore.
- Rehearse failed deployment rollback.
- Verify old image compatibility with forward-applied database changes.
- Measure RPO/RTO and record runbook.

### Exit gate

- Restore and rollback evidence is successful and repeatable.

---

## Phase 29 — Staging Acceptance and Security Review

### Objectives

Validate the release candidate in a production-like environment.

### Work and tests

- Deploy exact release image to staging.
- Use sanitized restored production data plus two quantity tenants.
- `T4`, `T5`, `T6`, selected `T7`, and `T8`.
- Tenant-isolation and authorization review.
- File-access review.
- SQL identifier/search-path review.
- Admin provisioning/type-lock review.
- User acceptance testing for wholesaler workflows and reports.
- Operational monitoring and alert verification.

### Exit gate

- Product owner, engineering, and operations approve the release candidate.
- No P0/P1 defect remains open.

---

## Phase 30 — Controlled Production Foundation Deployment

### Objectives

Deploy shared foundations while protecting existing paying customers.

### Pre-deployment

- Freeze release SHA.
- Verified backup and restore point.
- Maintenance notice/window.
- Tenant inventory and balances captured.
- Rollback owner and decision threshold assigned.

### Deployment

- Deploy through approval-gated CI/CD.
- Apply public migration: all existing companies serial-based.
- Verify type/schema-family agreement for every existing tenant.
- Apply serial hardening only to serial tenants.
- Do not create quantity pilot yet.

### Mandatory tests

- `T9`: login, permissions, subscription, purchase, sale, returns, payments,
  reports, attachments, admin for existing serial companies using
  production-safe checks.
- Compare captured critical balances/report totals.
- Monitor logs, 5xx, DB connections, CPU, memory, disk, health, and latency.

### Exit gate

- All existing companies operate exactly as before.
- If not, trigger the rehearsed rollback and incident process.

---

## Phase 31 — Quantity Pilot Provisioning

### Objectives

Introduce the first new quantity tenant without changing existing tenants.

### Work

- Create pilot company with quantity type, base currency, and tax mode.
- Verify quantity schema metadata/version/fingerprint.
- Configure warehouses, taxes, users, permissions, features, and opening data.
- Train pilot users.
- Import opening products/SKUs/stock only through validated tools.

### Mandatory tests

- `T9`: controlled purchase, sale, both returns, transfer, count, adjustment,
  payment/receipt, report, attachment, close-preview, and reconciliation.
- Verify serial tenants remain unaffected.
- Daily integrity report during pilot period.

### Exit gate

- Pilot accounting, stock, FIFO, warehouse balances, reports, and user workflow
  reconcile and receive owner/customer acceptance.

---

## Phase 32 — Observation, Support, and General Availability

### Objectives

Move from pilot to supported market operation.

### Work

- Enhanced monitoring for an agreed observation period.
- Daily backup verification.
- Daily tenant integrity/reconciliation.
- Track errors, slow reports, failed jobs, resource use, and support cases.
- Conduct first month-end close with supervised reconciliation.
- Fix defects through the same test gates.
- Update SRS, context, TODO, test results, runbooks, and release notes.
- Decide whether additional quantity companies may be onboarded.

### Mandatory tests

- `T9`: scheduled smoke checks.
- Repeat full serial/quantity CI for every hotfix.
- Post-month-close accounting and inventory reconciliation.

### Exit gate

- Observation period is stable.
- No unresolved data-integrity, isolation, security, or accounting defect.
- Product owner approves general availability.

---

## 7. Test Evidence Template

Every phase completion entry shall record:

```text
Phase:
Date:
Commit SHA:
Environment:
Schema families and versions:
Requirements covered:
Commands executed:
Passed:
Failed:
Expected failures:
Performance/resource observations:
Defects found:
Fix commits/patches:
Serial regression result:
Quantity result:
Isolation result:
Documentation updated:
Reviewer/approval:
```

Evidence shall be stored in a stable project test-results location rather than
only in terminal output.

---

## 8. Defect Severity and Gate Policy

| Severity | Examples | Gate effect |
|---|---|---|
| Critical | Tenant leakage, unbalanced journals, data loss, wrong FIFO/COGS, auth bypass, unrecoverable migration | Stop all dependent work and block release. |
| High | Negative stock, excessive returns, incorrect tax/currency, wrong party balance, unsafe edit | Block phase completion and release. |
| Medium | Incorrect report filter/export, confusing validation, non-critical permission/UI mismatch | Fix before staging unless explicitly deferred with owner approval. |
| Low | Cosmetic inconsistency without functional impact | May be scheduled, but must be documented. |

No accounting, tenant-isolation, security, backup, migration, or rollback defect
may be converted to an expected failure merely to keep CI green.

---

## 9. Rollback Principles

- Application rollback does not reverse public migrations or tenant SQL.
- All database changes shall use expand-and-contract compatibility.
- A release shall not drop or rename data required by the previous production
  image until the compatibility window has closed.
- Quantity provisioning shall remain feature-gated until its schema is ready.
- Existing serial tenants shall not be modified by quantity patches.
- A failed quantity pilot shall be disabled without affecting serial companies.
- Backup restoration is the last-resort recovery path and must be rehearsed.

---

## 10. Progress Reporting

After each phase, the implementation report shall state:

- Outcome first: passed, failed, or blocked.
- What changed.
- Which SRS requirements were implemented.
- Exact test evidence.
- Serial regression status.
- Quantity test status.
- New risks or decisions.
- Documents updated.
- Whether the next phase is authorized.
- Exact recommended Git commit title and body covering only that completed
  phase.

The next phase shall not start merely because code exists. Its predecessor’s
exit gate must pass.

The phase commit should be created before starting the next phase so each phase
has a recoverable, reviewable boundary. If unrelated user changes are present,
they shall not be included in the recommended phase commit.

---

## 11. Final Definition of Done

The quantity-company program is complete only when:

- Phases 0–32 have passed or an explicitly non-release phase has an approved
  deferral.
- Every P0/P1 SRS requirement maps to implementation and passing evidence.
- Existing serial companies operate without regression.
- The quantity pilot completes real operations and month-end reconciliation.
- Tenant isolation is proven under concurrency.
- FIFO, tax, discount, currency, stock, party, cash, and journal values
  reconcile.
- CI/CD blocks unsafe releases.
- ARM64 production execution is verified.
- Backup, restore, rollback, monitoring, and support processes operate.
- The SRS, plan, TODO, project context, fixed-issues log, test results, and
  deployment guides describe the released system accurately.
