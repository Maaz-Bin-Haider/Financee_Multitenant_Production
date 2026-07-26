# TODO

## [ ] MAJOR UPDATE: Add Quantity-Based Companies Without Disturbing Serial-Based Companies

### Objective

Financee currently supports serial-number-based inventory only. Every purchased
unit receives a serial number, and sales and returns operate on those individual
serialized units. This behavior is stable and must remain available without
functional or accounting regressions.

Add a second company type:

1. **Serial-based company** — provisions and uses the existing tenant schema and
   preserves all current behavior.
2. **Quantity-based company** — provisions a separate tenant schema designed
   around aggregate item quantities. Purchases, sales, purchase returns, and
   sale returns use manually entered quantities and never require serial
   numbers.

The admin company form must require the operator to choose the company type.
Once a company is provisioned, its type controls schema provisioning, backend
behavior, screens, validation, reports, and tests. Both types must use the same
visual theme and shared authentication, subscription, permissions, feature
flags, attachments, deployment, and administration infrastructure.

**Development requirements source of truth:**
`SRS_QUANTITY_BASED_COMPANY.md`. The SRS contains the approved Phase 0
requirements, traceable requirement IDs, serial-parity versus quantity-new
origins, reports, non-functional requirements, tests, CI/CD, rollout, and
acceptance criteria. This TODO tracks execution phases; implementation decisions
must remain consistent with the SRS.

**Implementation order and phase gates:**
`IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`. Its 33 phases (0–32) are the
authoritative execution order. Every phase requires implementation tests,
relevant serial regression tests, recorded evidence, and a passed exit gate
before the next dependent phase begins. The broader phases below remain the
high-level checklist and shall be updated from the detailed plan’s results.

### Detailed Plan Execution Status

> **PHASE 14 COMPLETE (2026-07-26):** Original-source quantity purchase
> returns now enforce eligible stock, preserve purchase cost, post exact
> AP/Cash/Inventory reversals, support guarded correction/reversal, serialize
> concurrency, and preserve serial behavior. Phase 15 is next.

> **PHASE 13 COMPLETE (2026-07-26):** Source-linked partial quantity sale
> returns now enforce cumulative limits, restore exact historical FIFO cost,
> support destination warehouses, reverse accounting, guard source sales,
> serialize concurrent returns, and preserve serial behavior. Phase 14 is next.

> **PHASE 12 COMPLETE (2026-07-26):** Domestic quantity sales now provide
> warehouse availability locking, exact FIFO COGS, cash/credit accounting,
> idempotency, guarded edit/reversal, navigation/summary, a quantity-specific
> UI, and complete serial/mixed-family regression evidence. Phase 13 is next.

> **CURRENT CHECKPOINT:** Phases 0–22 are complete. **Phase 23 — Complete
> Quantity Suite is next.** Phase 22 delivered the complete quantity report
> catalogue, reconciliation reports, quantity dashboards, filters,
> permissions/features, and CSV/Excel exports.
> Do not commit or push.

- [x] **Phase 0 — Requirements Baseline:** completed 2026-07-25.
- [x] **Phase 1 — Baseline Capture and Test Stabilization:** completed
  2026-07-25. All serial suites passed on two fresh isolated tenants; fixed the
  standalone HTTP false-green condition and bootstrap-tenant index drift. See
  `tests/PHASE1_BASELINE_RESULTS.md`.
- [x] **Phase 2 — Architecture and Schema-Family Design:** completed
  2026-07-25. Schema families, logical data model, FIFO/replay/locking,
  capability and payload contracts, precision, report reconciliation, rollback,
  and full SRS traceability are defined. See
  `ARCHITECTURE_QUANTITY_COMPANY.md`,
  `REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md`, and
  `tests/PHASE2_ARCHITECTURE_RESULTS.md`.
- [x] **Phase 3 — Public Company Metadata Migration:** completed 2026-07-25.
  Added immutable `Company.inventory_mode`, serial backfill, database
  constraint, safe admin behavior, and a Phase 5 quantity-provisioning gate.
  Upgrade, clean-install, rollback/reapply, focused metadata, and complete
  serial regressions passed. See `tests/PHASE3_COMPANY_METADATA_RESULTS.md`.
- [x] **Phase 4 — Currency Catalogue and Company Setup:** completed
  2026-07-25. Added the controlled worldwide currency catalogue, PKR/non-tax
  compatibility backfill, company base-currency/tax setup, activity locks,
  admin and provisioning support, and idempotent seeding. Upgrade,
  clean-install, rollback/reapply, and full serial regressions passed. See
  `tests/PHASE4_COMPANY_SETUP_RESULTS.md`.
- [x] **Phase 5 — Quantity Schema Foundation:** completed 2026-07-25.
  Added independent quantity template/hardening, central family registry,
  schema metadata/fingerprint verification, provisioning states and retry,
  family-filtered rollout, safe runtime gating, and mixed-family tests.
  Upgrade, clean provisioning, idempotency, mismatch denial, rollback/reapply,
  and full serial regressions passed. See
  `tests/PHASE5_QUANTITY_FOUNDATION_RESULTS.md`.
- [x] **Phase 6 — Accounting and Journal Foundation:** completed
  2026-07-25. Added quantity schema version 2 with the system chart of
  accounts, four-decimal double-entry ledger, atomic posting and reversal,
  immutable posted journals, deferred database balance enforcement, trial
  balance/account lookup, concurrency-safe document numbering, idempotent
  rollout, and tenant-isolation tests. See
  `tests/PHASE6_ACCOUNTING_FOUNDATION_RESULTS.md`.
- [x] **Phase 7 — Product, Variant, SKU, and Unit Masters:** completed
  2026-07-25. Added quantity schema version 3, six controlled units, normalized
  product and seven-dimension variant identity, collision-safe SKU suggestion,
  manual SKU and unit transaction locks, exact unit precision enforcement,
  active/inactive catalogue behavior, a quantity-only JSON API slice, and
  tenant/permission isolation tests. See
  `tests/PHASE7_ITEM_MASTER_RESULTS.md`.
- [x] **Phase 8 — Warehouse Foundation:** completed 2026-07-25.
  Added quantity schema version 4, normalized multi-warehouse identity,
  serialized single-default selection and reassignment, active/inactive
  lifecycle, reference-protected deletion, explicit Django permissions,
  quantity-only lookup/mutation APIs, cumulative fresh-schema upgrades, and
  tenant/family isolation tests. See `tests/PHASE8_WAREHOUSE_RESULTS.md`.
- [x] **Phase 9 — Stock Movement and FIFO Engine:** completed
  2026-07-25. Added quantity schema version 5 with an immutable stock movement
  ledger, per-SKU/per-warehouse balance projection, FIFO layers and durable
  outbound allocations, current/historical availability, deterministic
  backdated replay, historical negative-stock denial, canonical scope locking,
  guarded reversals, and movement/balance/FIFO reconciliation. The focused
  suite passed 38/38 and all serial regressions remained green. No invoice UI
  was enabled. See `tests/PHASE9_FIFO_ENGINE_RESULTS.md`.
- [x] **Phase 10 — Opening Stock:** completed 2026-07-25.
  Added quantity schema version 6 with immutable opening-stock documents,
  OPN numbering, whole/decimal SKU and warehouse lines, atomic FIFO movements,
  Inventory/Opening Balance journals, guarded untouched-layer reversal,
  Opening Balance status and Capital reclassification, and a quantity-specific
  UI using the existing theme. The focused suite passed 37/37 and all serial
  regressions remained green. See
  `tests/PHASE10_OPENING_STOCK_RESULTS.md`.
- [x] **Phase 11 — Quantity Purchases:** completed 2026-07-25.
  Added quantity schema version 7 with domestic credit/cash purchase documents,
  required vendor snapshots, PUR numbering, SKU/warehouse quantity lines,
  atomic FIFO and Inventory/AP/Cash journals, database-serialized idempotency,
  audited guarded edits with historical replay, guarded reversal,
  navigation/summary, and a no-serial quantity purchase UI. The focused suite
  passed 46/46 and all serial regressions remained green. See
  `tests/PHASE11_QUANTITY_PURCHASES_RESULTS.md`.
- [x] **Phase 12 — Quantity Sales:** completed 2026-07-26.
  Added quantity schema version 8 with immutable domestic credit/cash sale
  documents, SAL numbering, manual SKU/warehouse quantities, atomic
  availability locking, durable FIFO allocations, exact AR/Cash/Revenue and
  COGS/Inventory journals, idempotency, audited guarded edits, reversal,
  navigation/summary, and a no-serial sales UI. The focused suite passed 34/34,
  all 25 mixed-family modules passed, and complete serial regressions remained
  green. See `tests/PHASE12_QUANTITY_SALES_RESULTS.md`.
- [x] **Phase 13 — Quantity Sale Returns:** completed 2026-07-26.
  Added quantity schema version 9 with source-linked partial returns,
  cumulative limits, exact FIFO allocation restoration, destination
  warehouses, accounting reversal, source-sale guards, idempotency, guarded
  update/reversal, navigation/summary, and a no-serial UI. Focused tests passed
  23/23 and all serial/mixed-family gates remained green. See
  `tests/PHASE13_QUANTITY_SALE_RETURNS_RESULTS.md`.
- [x] **Phase 14 — Quantity Purchase Returns:** completed 2026-07-26.
  Added quantity schema version 10 with persistent original-source allocation
  directives, source-aware FIFO replay, original purchase-cost valuation,
  AP/Cash/Inventory reversal accounting, idempotency, guarded correction and
  reversal, concurrency control, navigation/summary, and a no-serial UI.
  Focused tests passed 22/22 and all 27 mixed-family modules plus complete
  serial gates remained green. See
  `tests/PHASE14_QUANTITY_PURCHASE_RETURNS_RESULTS.md`.
- [x] **Phase 15 — Warehouse Transfers:** completed 2026-07-26.
  Added quantity schema version 11 with atomic source/destination movements,
  preserved FIFO cost segments and lineage, company-value neutrality, explicit
  permissions, idempotency, guarded correction/reversal, concurrency control,
  navigation/summary, and quantity UI. Focused tests passed 19/19; all 28
  modules and complete serial gates remained green. See
  `tests/PHASE15_QUANTITY_TRANSFERS_RESULTS.md`.
- [x] **Phase 16 — Physical Counts and Adjustments:** completed 2026-07-26.
  Added quantity schema version 12 with reproducible cutoff snapshots,
  approval-only posting, FIFO-valued shortages, entered-cost surpluses,
  Inventory Adjustment Gain/Loss journals, guarded reversal, explicit
  permissions, idempotency, navigation/summary, and quantity UI. Focused tests
  passed 17/17; all 29 modules and complete serial gates remained green. See
  `tests/PHASE16_QUANTITY_COUNTS_ADJUSTMENTS_RESULTS.md`.
- [x] **Phase 17 — Tax and Discount Engine:** completed 2026-07-26.
  Added quantity schema version 13 tax-environment metadata, validated tenant
  tax codes/control accounts, immutable calculation snapshot fields, and the
  canonical line/invoice discount plus inclusive/exclusive tax calculator.
  Purchases, sales, both returns, control journals, guarded revisions/reversals,
  and administration/UI are integrated. Focused tests passed 26/26; all 30
  mixed-family modules, HTTP 70/70, system 111/111, and deep serial 2702/2702
  passed. See `tests/PHASE17_QUANTITY_TAX_DISCOUNTS_RESULTS.md`.
- [x] **Phase 18 — Multi-Currency and Realized Gain/Loss:** completed
  2026-07-26. Added schema v14 immutable transaction/base snapshots, foreign
  purchase and sale posting, cash/bank payment and receipt allocations,
  partial/final settlements, realized gain/loss journals and reporting,
  return/settlement guards, and UI. Focused tests passed 23/23; all 31
  mixed-family modules, HTTP 70/70, system 111/111, and deep serial 2702/2702
  passed. See `tests/PHASE18_QUANTITY_CURRENCY_RESULTS.md`.
- [x] **Phase 19 — Shared Financial Modules and Month Close:** completed
  2026-07-26. Added quantity parties and opening balances, payments, receipts,
  contra, opening cash, owner equity, month preview/close/reversal, shared UI
  compatibility, and universal close guards for quantity inventory and
  financial mutations. Focused tests passed 27/27; all 32 mixed-family modules,
  HTTP 70/70, system 111/111, and deep serial 2702/2702 passed. See
  `tests/PHASE19_QUANTITY_FINANCIAL_MODULES_RESULTS.md`.
- [x] **Phase 20 — Attachments, Descriptions, Audit, Permissions, and
  Features:** completed 2026-07-26. Added quantity document attachments and
  cleanup, smart descriptions, immutable mutation audit, permission-gated
  audit UI/API, type-aware features, and shared subscription enforcement.
  Focused tests passed 19/19 and all 33 mixed-family modules passed. See
  `tests/PHASE20_QUANTITY_PLATFORM_CONTROLS_RESULTS.md`.
- [x] **Phase 21 — Type-Aware Backend and Quantity UI:** completed
  2026-07-26. Centralized company-mode capabilities and route dispatch, blocked
  cross-family payload bypasses, added authoritative previews and warehouse
  management, and standardized loading, duplicate submission, Alerts,
  keyboard, responsive, and accessibility behavior. Focused checks passed
  14/14 and all 34 mixed-family modules passed. See
  `tests/PHASE21_TYPE_AWARE_UI_RESULTS.md`.
- [x] **Phase 22 — Quantity Reports and Dashboards:** completed 2026-07-26.
  Added schema v22 reporting/filter/dashboard contracts, a central 40-report
  availability catalogue, accounts/stock/FIFO/sales/purchase/return and
  reconciliation coverage, permission/feature enforcement, responsive UI,
  and CSV plus Excel exports. Focused checks passed 25/25 and all 35
  mixed-family modules passed. See
  `tests/PHASE22_QUANTITY_REPORTS_DASHBOARDS_RESULTS.md`.
- [ ] Phases 23–32: not started; see
  `IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`.

### Non-Negotiable Requirements

- Do not rewrite, weaken, or remove the existing serial-based workflow.
- Existing companies must remain serial-based after deployment unless an
  explicit, separately designed migration is approved.
- Company type must not be silently changeable after business data exists.
- Serial and quantity tenants must have separate schema templates, schema
  versions, hardening scripts, and upgrade paths.
- All accounting rules must remain equivalent: balanced double-entry journals,
  accounts receivable/payable, cash behavior, revenue, inventory, COGS,
  returns, owner equity, opening balances, and month close.
- Tenant type must be resolved from the trusted public `Company` record, never
  from browser input.
- Every request and management command must continue to enforce tenant
  isolation and reset PostgreSQL `search_path`.
- All schema changes must support fresh provisioning and idempotent upgrades of
  existing tenants.
- No production integration may begin until the isolated four-company test
  matrix and rollback rehearsal pass.

---

### Phase 0 — Requirements, Decisions, and Acceptance Criteria — COMPLETE

**Started:** 2026-07-25

**Completed:** 2026-07-25

**Current status:** All owner decisions in the Phase 0 Decision Worksheet have
been approved and recorded. Phase 1 architecture and data-model design may
begin, but no live-system change is authorized by completion of this phase.

- [x] Document the exact quantity inventory rules before designing SQL:
  - Whether fractional quantities are supported, and the decimal precision.
  - Whether negative stock is always prohibited.
  - Whether backdated purchases, sales, and returns are allowed.
  - Whether stock is tracked globally or by warehouse/location.
  - Whether batch, lot, expiry-date, size, color, or unit-of-measure tracking is
    required now or reserved for a later version.
  - Whether one item may use multiple units of measure and conversions.
  - Whether overselling during simultaneous requests must block immediately.
- [x] Select and document the quantity-based inventory costing method:
  weighted-average, FIFO, or another approved method. Define how backdated
  edits, returns, and purchase price changes affect historical COGS.
- [x] Define sale-return valuation: restore the exact cost originally charged
  to the sale, not the item's current cost, unless a different accounting rule
  is explicitly approved.
- [x] Define purchase-return valuation and the guard when some purchased stock
  has already been sold.
- [x] Decide whether serial and quantity modes are permanently exclusive per
  company. The initial implementation should treat company type as immutable.
- [x] Decide how invoice edits behave after downstream transactions exist.
- [x] Define rounding rules for quantities, unit prices, tax, totals, COGS, and
  journal lines.
- [x] Produce written acceptance criteria and realistic examples for purchase →
  partial sale → sale return → resale → purchase return → month close.
- [x] Record the approved decisions in `PROJECT_CONTEXT.md` before development
  begins.

**Phase gate:** No schema or backend implementation starts until costing,
quantity precision, negative-stock, backdating, return valuation, and company
type immutability are approved.

---

### Phase 1 — Architecture and Data-Model Design

- [ ] Add an immutable `inventory_mode`/`company_type` field to the public
  `Company` model with explicit `serial` and `quantity` choices.
- [ ] Create a safe public-schema migration:
  - Existing companies are backfilled as `serial`.
  - New company creation requires an explicit type.
  - Changing type after provisioning is blocked by model/admin validation.
  - Audit the selected type during company creation.
- [ ] Update the custom admin company form with a clear company-type selector
  and descriptions of both modes.
- [ ] Add an admin confirmation warning that company type cannot be changed
  after schema provisioning.
- [ ] Design a schema-family registry instead of scattering type checks:
  provisioning template, required schema version, hardening file, supported
  routes, report catalogue, and feature catalogue must be selected centrally.
- [ ] Keep the existing serial schema and SQL behavior as the serial-family
  source of truth.
- [ ] Create independently named quantity-family SQL artifacts, for example:
  - `quantity_tenant_template.sql`
  - `quantity_production_hardening.sql`
  - idempotent quantity-schema patch files
- [ ] Add separate schema-version requirements for serial and quantity tenants.
- [ ] Update provisioning so a company schema is built atomically from the
  correct template; a failed provision must not leave an apparently usable
  company.
- [ ] Add schema fingerprint/type metadata inside every tenant schema and verify
  that it agrees with the public `Company.company_type` before activation.
- [ ] Design an explicit compatibility policy so an old application image can
  safely run during deployment rollback after database upgrades.
- [ ] Create architecture diagrams and table/function/report catalogues for both
  schema families.

**Phase gate:** Architecture review confirms there is no path that provisions a
quantity company from the serial template or activates a schema whose recorded
type disagrees with the company record.

---

### Phase 2 — Design the Complete Quantity-Based Tenant Schema

- [ ] Design quantity equivalents for all master and accounting tables.
- [ ] Preserve shared business concepts where appropriate: parties, items,
  chart of accounts, journal entries, journal lines, invoice headers, payments,
  receipts, contra, opening cash, owner equity, month close, subscriptions,
  feature flags, descriptions, and attachments.
- [ ] Replace per-unit serial tables and relationships with quantity movement
  and cost-layer structures suitable for the approved costing method.
- [ ] Store an immutable stock movement trail for:
  - Opening stock
  - Purchase
  - Purchase return
  - Sale
  - Sale return
  - Adjustment, if adjustments are approved
- [ ] Ensure every movement records item, quantity, direction, date, source
  document, source line, cost basis, user, and creation timestamp.
- [ ] Add database constraints for positive quantities, valid prices, valid
  movement direction, valid document relationships, and non-empty journal
  entries.
- [ ] Add row-level locking/concurrency rules that prevent two simultaneous
  sales from consuming the same available quantity.
- [ ] Implement idempotency or duplicate-submission protection for invoice and
  cash-movement posting.
- [ ] Implement quantity purchase functions:
  create, fetch, navigate, summarize, validate update, update, and guarded
  delete.
- [ ] Implement quantity sale functions:
  available-stock validation, create, fetch, navigate, summarize, update, and
  guarded delete.
- [ ] Implement partial and full quantity sale-return functions with original
  sale-line and cost-basis linkage.
- [ ] Implement partial and full quantity purchase-return functions with
  vendor/purchase linkage and available-quantity guards.
- [ ] Prevent cumulative returns from exceeding the original transaction
  quantity.
- [ ] Define and enforce downstream mutation rules after sale or return activity.
- [ ] Implement opening-stock, stock reclassification, payments, receipts,
  contra, owner equity, month close, and dashboard functions for quantity
  tenants.
- [ ] Preserve cash-sale/cash-purchase accounting and sentinel-party behavior
  without exposing cash parties as normal credit customers/vendors.
- [ ] Implement attachments and descriptions for every supported quantity
  document.
- [ ] Add indexes based on realistic report and transaction query plans.
- [ ] Create fresh-provision, rerunnable-hardening, upgrade, and consistency
  checks for the quantity schema.

**Required accounting invariants:**

- [ ] Every posting leaves total debit equal to total credit.
- [ ] Inventory asset equals the value implied by the approved costing method.
- [ ] Revenue and COGS are correct for partial and multi-line sales.
- [ ] Sale returns reverse revenue/receivable or cash and restore the original
  cost basis correctly.
- [ ] Purchase returns reduce inventory and payable/cash correctly.
- [ ] Party balances reconcile with journal lines.
- [ ] Stock on hand equals opening + purchases + sale returns - sales -
  purchase returns, subject to any approved adjustments.
- [ ] No transaction can create negative stock unless Phase 0 explicitly allows
  it.
- [ ] Closed periods reject every prohibited write path.

---

### Phase 3 — Backend Integration for Both Schema Families

- [ ] Introduce a schema-capability/service layer that selects serial or
  quantity operations from the authenticated tenant's trusted company type.
- [ ] Avoid large duplicated view modules where request parsing, permissions,
  attachments, and responses can be safely shared.
- [ ] Keep inventory-specific SQL calls and payload validation explicitly
  separated so quantity payloads cannot reach serial functions and vice versa.
- [ ] Update purchase, sale, purchase-return, sale-return, opening-stock,
  dashboard, and report views for company-type-aware behavior.
- [ ] Preserve all current URL permissions or introduce versioned/type-specific
  endpoints with an explicit compatibility plan.
- [ ] Reject serial fields for quantity tenants and reject quantity-only
  payloads that bypass required serial selection in serial tenants.
- [ ] Ensure all errors remain sanitized and useful to users.
- [ ] Update attachment access checks for documents in both schema families.
- [ ] Update admin activity reporting so both document models appear in a
  consistent audit trail.
- [ ] Update feature flags so unsupported reports cannot be enabled for the
  wrong company type.
- [ ] Add structured audit events for company creation/type, posting, update,
  deletion, reversal, return, export, and authorization failure.

---

### Phase 4 — Quantity-Based User Interface

- [ ] Keep the existing theme, navigation conventions, alerts, permissions, and
  responsive behavior.
- [ ] Preserve current serial screens for serial companies without regression.
- [ ] For quantity companies, replace serial entry/lookup controls with manual
  quantity fields and clear available-stock indicators.
- [ ] Add quantity validation and decimal precision consistently on client and
  server; PostgreSQL remains authoritative.
- [ ] Redesign purchase entry for item, quantity, unit cost, totals, description,
  and attachments.
- [ ] Redesign sale entry for item, available quantity, sale quantity, unit
  price, totals, description, and attachments.
- [ ] Redesign returns to select original invoice lines and enforce remaining
  returnable quantities.
- [ ] Prevent double submission while a document is being posted.
- [ ] Make the company inventory mode visible but unobtrusive in the UI.
- [ ] Verify keyboard entry, spreadsheet paste where supported, mobile layout,
  accessibility, printing, CSV export, and browser refresh/retry behavior.

---

### Phase 5 — Redesign Reports for Quantity-Based Companies

#### Accounts Reports to Retain/Adapt

- [ ] Trial Balance — unchanged accounting purpose.
- [ ] Detailed Party Ledger — adapted invoice details to quantities rather than
  serial lists.
- [ ] Cash Ledger — retained.
- [ ] Accounts Receivable — retained.
- [ ] Accounts Payable — retained.
- [ ] Monthly Company Position — retained and validated against quantity stock
  valuation.
- [ ] Monthly Income Statement — retained with quantity-based COGS.

#### Stock Reports to Retain/Redesign

- [ ] Stock Summary — item-level opening, purchased, sold, returned, adjusted,
  and closing quantities.
- [ ] Stock Valuation — quantity on hand, unit cost/average cost or remaining
  cost layers, and total inventory value.
- [ ] Item Movement Ledger — chronological quantity-in, quantity-out, running
  quantity, unit cost, and source document.
- [ ] Item Transaction History — purchase/sale/return history by item and date.
- [ ] Last Purchase and Last Sale — item-level latest transaction information.
- [ ] Low Stock Report — current quantity against an optional reorder level.
- [ ] Dead/Slow-Moving Stock — quantities without sales for a selected period.
- [ ] Negative/Integrity Exception Report — any impossible quantity or value
  state; expected to remain empty.

#### Sales Reports to Retain/Redesign

- [ ] Sales Summary — quantity, gross sales, returns, net sales, COGS, and gross
  profit.
- [ ] Product Profitability — quantity sold, average selling price, COGS, gross
  profit, and margin.
- [ ] Customer Profitability — retained using quantity sale lines.
- [ ] Sales by Product — redesigned around units/quantities rather than serials.
- [ ] Sales by Customer — retained.
- [ ] Sale-Wise Profit — invoice/line quantity, revenue, cost, and profit.
- [ ] Sales Trend — retained.
- [ ] Invoice Register — retained with total quantities and values.
- [ ] Purchase and Sale Return Analysis — new report showing return rate,
  quantity, value, item, customer/vendor, and source invoice.

#### Reports Dropped for Quantity Companies

- [ ] Drop **Serial Ledger** because quantity companies have no individual
  serial identity to trace.
- [ ] Drop **Serial Ledger with Sold Flag** because sold status exists as
  aggregate movement quantities, not per unit.
- [ ] Drop **Serial Purchase-Only Ledger** because purchases are traced through
  item movement and purchase-line reports.
- [ ] Drop **Serial Sale-Only Ledger** because sales are traced through item
  movement and sale-line reports.
- [ ] Drop **Serial Number Details/Lookup** because no serial number exists.

These reports remain fully available to serial-based companies. Their quantity
replacements are the Item Movement Ledger, Stock Summary, Stock Valuation, and
line-level purchase/sale/return reports.

#### New Quantity Reports and Benefits

- [ ] **Inventory Movement Reconciliation** — proves that every item's opening
  plus inward movements minus outward movements equals closing stock.
- [ ] **Inventory Valuation Reconciliation** — reconciles stock value to the
  Inventory control account and exposes accounting drift.
- [ ] **Stock Aging** — identifies capital tied up in old stock.
- [ ] **Reorder Report** — helps companies replenish items before stockouts.
- [ ] **Gross Margin by Item/Category/Customer** — helps pricing and sales
  decisions.
- [ ] **Return Rate Analysis** — highlights problematic products, vendors, or
  customers.
- [ ] **Purchase Price Variance** — shows changing acquisition costs and margin
  pressure.
- [ ] **Fast/Slow Moving Items** — supports purchasing and inventory planning.

- [ ] Define report availability centrally by company type.
- [ ] Hide unsupported report navigation and block direct endpoint access.
- [ ] Add CSV/Excel export tests for every supported quantity report.
- [ ] Reconcile report totals to source transactions and journal balances, not
  merely HTTP success.

---

### Phase 6 — Complete Test Suite for the Quantity Schema

- [ ] Build a new first-principles quantity-schema harness; do not obtain green
  results by weakening serial-suite assertions.
- [ ] Test every stored function, trigger, view, constraint, and report.
- [ ] Cover parties of every type, items, opening balances, opening stock,
  purchases, sales, both returns, payments, receipts, contra, owner equity,
  month close, dashboards, descriptions, attachments, permissions,
  subscriptions, feature flags, exports, and admin workflows.
- [ ] Test realistic quantity flows:
  - Purchase 100, sell 30, return 5 from the sale, resell 3.
  - Purchase the same item at multiple costs.
  - Partial and full purchase returns.
  - Multiple sale returns against one invoice.
  - One return spanning eligible lines/invoices if approved.
  - Cash and credit purchases/sales.
  - Backdated edits and returns according to the approved rules.
  - Month close and attempted post-close mutation.
- [ ] Test invalid and hostile flows:
  zero/negative quantity, excessive quantity, excessive cumulative return,
  unknown item/party, mismatched customer/vendor, duplicate submission,
  malformed JSON, unauthorized route, feature-disabled route, attachment
  abuse, and direct cross-mode payloads.
- [ ] Add real concurrent transaction tests for overselling, duplicate return,
  simultaneous invoice edits, and retry/idempotency behavior.
- [ ] Assert double-entry balance, exact party balances, inventory value, COGS,
  revenue, cash, stock quantity, returnable quantity, and no empty journals at
  every checkpoint.
- [ ] Test fresh quantity provisioning and repeated hardening.
- [ ] Test quantity schema upgrades from every released quantity schema version.
- [ ] Run the existing serial suites unchanged and require all to pass.
- [ ] Update test documentation with exact checks and latest verified totals.

---

### Phase 7 — Isolated Dual-Mode Integration Environment

- [ ] Create an isolated Docker/staging environment with no connection to the
  live database or live media.
- [ ] Provision exactly four companies:
  - Serial Company A
  - Serial Company B
  - Quantity Company A
  - Quantity Company B
- [ ] Create representative users, roles, subscriptions, feature settings, and
  attachments for all four.
- [ ] Run all existing serial tests against both serial companies.
- [ ] Run the complete quantity suite against both quantity companies.
- [ ] Run HTTP/UI tests through the real middleware and permission stack for all
  four companies.
- [ ] Perform simultaneous purchases, sales, returns, payments, report reads,
  exports, and attachment downloads across all four companies.
- [ ] Verify no table rows, report totals, files, cache keys, errors, or
  `search_path` state leak between:
  - The two serial tenants
  - The two quantity tenants
  - Serial and quantity tenants
  - Tenant and public schemas
- [ ] Test persistent Gunicorn connections and concurrent threads because
  tenant activation is connection-sensitive.
- [ ] Test failures/exceptions during concurrent requests and prove the
  connection resets to `public`.
- [ ] Compare accounting and report results to independently calculated
  expected values.
- [ ] Run performance and memory tests sized for the production `t4g.medium`
  ARM64 host.

**Phase gate:** Zero unexplained failures, zero tenant leakage, zero serial
regressions, and all accounting reconciliations pass.

---

### Phase 8 — CI/CD and Deployment Changes

- [ ] Extend CI to provision the four-company/two-mode matrix on every relevant
  pull request and main-branch build.
- [ ] Run serial and quantity suites as separately visible CI stages.
- [ ] Add schema-template consistency and schema-version checks for both
  families.
- [ ] Add migration checks for the new public `Company` field.
- [ ] Add ARM64 smoke tests for the actual image architecture deployed to the
  `t4g.medium`.
- [ ] Validate that the published multi-architecture image contains both
  `linux/amd64` and `linux/arm64`.
- [ ] Add pre-deployment backup and restore verification.
- [ ] Add a deployment preflight that inventories every company, expected type,
  schema type, and current schema version.
- [ ] Apply serial hardening only to serial schemas and quantity hardening only
  to quantity schemas.
- [ ] Fail safely and report the exact tenant if a schema upgrade fails; do not
  silently leave a partial rollout.
- [ ] Add post-deployment smoke tests for at least one tenant of each type.
- [ ] Keep manual production approval.
- [ ] Rehearse application rollback while retaining forward-compatible database
  changes.
- [ ] Document recovery if company type and schema type ever disagree.

---

### Phase 9 — Production-Readiness Review

- [ ] Freeze the candidate release and run the entire test matrix from a clean
  database.
- [ ] Restore a sanitized production backup into staging and rehearse the
  upgrade.
- [ ] Verify all existing companies are classified as serial and unchanged.
- [ ] Compare critical serial workflows and report totals before and after the
  upgrade.
- [ ] Verify backup, restore, monitoring, disk capacity, database capacity, and
  rollback procedures.
- [ ] Complete a security review focused on tenant/type isolation, permissions,
  attachment access, SQL identifier safety, and admin company provisioning.
- [ ] Produce operator documentation, user documentation, release notes,
  supported-report matrices, and known limitations.
- [ ] Obtain explicit approval that the release is safe to integrate with the
  live system.

**Phase gate:** Confirm “ready for live integration” only after evidence from
tests, staging, backup/restore, security, performance, and rollback rehearsal.

---

### Phase 10 — Controlled Live Integration and Verification

- [ ] Take and verify a complete off-server database and media backup.
- [ ] Schedule a maintenance window and notify current customers.
- [ ] Deploy the approved, SHA-pinned ARM64-compatible image through CI/CD.
- [ ] Apply the public migration that marks all existing companies as serial.
- [ ] Run serial hardening only against existing serial schemas.
- [ ] Verify every existing company, membership, schema type, schema version,
  subscription, permission, and feature setting.
- [ ] Run production-safe smoke tests for login, purchase, sale, returns,
  payments, reports, attachments, and admin access.
- [ ] Confirm all existing serial-company totals and workflows remain correct.
- [ ] Create the first quantity company only after existing-company
  verification passes.
- [ ] Provision and verify the new quantity schema, permissions, sample
  transactions, reports, attachments, and accounting reconciliation.
- [ ] Monitor errors, latency, CPU credits, memory, disk, PostgreSQL connections,
  and container restarts closely after release.
- [ ] Keep the rollback decision window open and document final verification.
- [ ] Update `README.md`, `PROJECT_CONTEXT.md`, `FIXED_ISSUES.md` (if issues are
  found), deployment documentation, test results, and this TODO.

---

### Additional Beneficial Work

- [ ] Add staging as a permanent environment matching production architecture.
- [ ] Add encrypted automated backups and routine restore drills before this
  major database change.
- [ ] Add centralized structured logs, request IDs, tenant identifiers, error
  tracking, and alerts without logging sensitive financial payloads.
- [ ] Add an immutable audit log for company creation/type selection and all
  financial mutations.
- [ ] Add tenant export and offboarding tools for both company types.
- [ ] Add database query-plan/performance regression tests for growing quantity
  movement tables.
- [ ] Add data-integrity health checks that administrators can run per tenant.
- [ ] Version API/payload contracts used by the JavaScript frontend.
- [ ] Remove or quarantine obsolete ZIP patches and commented legacy
  implementations after confirming they are no longer needed.

### Questions Requiring Owner Approval

- [x] Which costing method must quantity companies use: weighted-average or
  FIFO?
- [x] Are fractional quantities required? If yes, what maximum precision?
- [x] Must negative stock always be blocked?
- [x] Are warehouse/location, batch/lot, expiry date, size/color variants, and
  units of measure required in the first quantity release?
- [x] Can invoices be backdated or edited after later stock movements?
- [x] Should quantity companies support inventory adjustments and stock counts
  in the first release?
- [x] Must invoice numbering be sequential per company and document type?
- [x] Should company type be permanently immutable, or is a separately approved
  serial-to-quantity conversion required later?
- [x] What maximum concurrent users, item count, transaction count, and report
  response time should the release support?
- [x] Which reports are contractually required by the three current customers?

### Phase 0 Decision Worksheet

Reply with the question number and your selected answer. The recommended
defaults are designed for the safest first release and can be changed before
the Phase 0 gate is approved.

1. **Inventory costing method**
   - Recommended: **perpetual weighted-average cost**.
   - Alternative: FIFO cost layers.
   - Decision: **APPROVED — FIFO cost layers**.

2. **Quantity precision**
   - Approved units include Pieces, Boxes, Kilograms, Grams, Litres, and Metres.
   - Pieces and Boxes use whole-number quantities only.
   - Weight, volume, and length items support up to three decimal places.
   - Decision: **APPROVED — per-item unit rules with `numeric(18, 3)` quantity
     precision; Pieces and Boxes must have a zero fractional part**.

3. **Negative stock**
   - Never allow a sale, purchase return, edit, deletion, transfer, adjustment,
     or backdated transaction to make stock negative.
   - Show a clear warning with available and requested quantity, but the warning
     must not provide an override that permits negative stock.
   - Decision: **APPROVED — block negative stock with user warnings**.

4. **Warehouses and locations**
   - Quantity companies require multiple warehouses in the first release.
   - Purchases, sales, returns, opening stock, transfers, adjustments, counts,
     availability checks, and stock reports must be warehouse-aware.
   - Decision: **APPROVED — multi-warehouse in the first release**.

5. **Batch, lot, and expiry tracking**
   - Decision: **APPROVED — exclude batch, lot, and expiry tracking**.

6. **Item variants**
    - Quantity companies require item variants.
    - Required variant dimensions: brand, model, color, storage, RAM, region, and
      condition.
    - Every unique sellable variant combination receives a unique SKU.
    - The system suggests the SKU automatically; an authorized user may enter
      or edit it manually only before the item/variant has transactions.
    - Decision: **APPROVED — required dimensions and SKU identity/lifecycle
      confirmed**.

7. **Units of measure**
   - No unit conversion is required. Each item/variant has one inventory unit.
   - A product stocked as Pieces and a product stocked as Boxes must be separate
     item/SKU records unless a later conversion feature is approved.
   - Decision: **APPROVED — one unit per item/variant, no conversions**.

8. **Backdated transactions**
   - Backdated transactions are required.
   - They must be limited to open periods and must recompute affected FIFO
     layers, COGS, stock balances, and reports safely.
   - Any backdated operation that would create temporary/final negative stock or
     invalidate later consumption must be blocked with an explanation.
   - Decision: **APPROVED IN PRINCIPLE — backdating allowed with open-period,
     FIFO-reflow, and non-negative-stock guards**.

9. **Editing posted documents**
   - Posted invoices must be editable.
   - Edits must atomically rebuild affected FIFO layers, stock movements,
     journals, party balances, COGS, and reports.
   - An edit must be blocked when downstream transactions cannot be preserved
     safely; the UI must state why it is blocked.
   - Decision: **APPROVED IN PRINCIPLE — guarded posted-document editing**.

10. **Sale-return valuation**
    - Recommended: reverse the exact historical COGS assigned to the original
      sale line and restore that value to inventory.
    - Decision: **APPROVED — restore the exact original FIFO cost**.

11. **Purchase-return valuation**
    - Recommended: return at the original purchase-line unit cost and block the
      return if sufficient eligible stock from that purchase cannot be
      established under the selected costing model.
    - Decision: **APPROVED — original purchase cost with FIFO eligibility
      guard**.

12. **Cumulative return rules**
    - Recommended: allow multiple partial returns, but never allow total sale or
      purchase returns to exceed the original line quantity.
    - Decision: **APPROVED — partial returns allowed; cumulative quantity may
      never exceed the original line quantity**.

13. **Inventory adjustments and physical stock counts**
    - Physical stock counts are required in the first release.
    - The system must compare counted and system quantities per
      warehouse/item/variant and post an approved adjustment for differences.
    - Adjustments require a reason, permission, FIFO valuation rule, balanced
      journal, and immutable audit trail.
    - Decision: **APPROVED — physical counts and controlled adjustments**.

14. **Company-type immutability**
    - Recommended: company type is permanently immutable after provisioning.
      Any future serial-to-quantity conversion must be a separate migration
      project that creates and reconciles a new schema.
    - Decision: **APPROVED — company type is permanently locked after
      provisioning**.

15. **Document numbering**
    - Recommended: sequential document numbers per tenant and document type,
      generated transactionally by PostgreSQL; deleted/voided numbers are never
      reused.
    - Alternative: retain only the current database IDs.
    - Decision: **APPROVED — separate sequences per document type, such as
      `SAL-000001`, `PUR-000001`, and `SR-000001`**.

16. **Taxes, discounts, and currency**
    - Taxes, discounts, and multiple currencies are required in this update.
    - Both percentage and fixed-amount discounts are required.
    - Discounts must be supported at both line and whole-invoice level.
    - Discounts reduce taxable value before tax by default. Store the applied
      discount values and calculation basis permanently on the invoice so later
      configuration changes cannot alter historical documents.
    - Tax names, codes, and percentages are configurable per company.
    - During company creation, the admin selects whether the company operates in
      a tax-based or non-tax environment.
    - Tax-based companies support tax-inclusive and tax-exclusive pricing, with
      a company default and invoice-level selection.
    - Calculate tax per invoice line and show summarized tax totals on the
      invoice.
    - Support taxable, zero-rated, and exempt lines, with an optional exemption
      reason/reference.
    - A company's base currency must be selected during admin company creation;
      the selectable catalogue must support world currencies.
    - For an international purchase or sale whose transaction currency differs
      from the company's base currency, the exchange rate is entered manually
      on that invoice and stored permanently with the posting.
    - Domestic/base-currency invoices do not request an exchange rate.
    - Store the transaction currency, foreign amount, invoice exchange rate, and
      calculated base-currency amount permanently.
    - Payments and receipts against foreign invoices require the settlement
      exchange rate.
    - Automatically calculate realized exchange gains/losses, including
      proportional calculations for partial payments and receipts.
    - Show realized exchange gains/losses in profit and expense reports.
    - Do not perform month-end unrealized revaluation. Unpaid foreign invoices
      remain at their original posted base-currency value until settlement.
    - Decision: **APPROVED — tax environment/calculation, discounts,
      base-currency selection, manual foreign-invoice and settlement rates, and
      realized-only exchange gain/loss treatment confirmed**.

17. **Initial scale target**
    - Recommended minimum target per tenant: 100 concurrent active sessions,
      100,000 item records, 5 million stock movements, and normal reports under
      3 seconds with heavy exports handled separately.
    - This target may require a larger host than the current `t4g.medium`; load
      testing will determine the production capacity.
    - Decision: **APPROVED — validate 100 concurrent sessions, 100,000 SKUs,
      five million stock movements, and ordinary reports under three seconds**.

18. **Required reports**
    - Recommended baseline: all retained/adapted accounts and sales reports plus
      Stock Summary, Stock Valuation, Item Movement Ledger, Inventory Movement
      Reconciliation, Inventory Valuation Reconciliation, Stock Aging, Reorder,
      Gross Margin, Return Rate, Purchase Price Variance, and Fast/Slow Moving
      Items.
    - The full recommended quantity report catalogue is approved in addition to
      daily sales, month-end profit, expenses, purchases, and stock reporting.
    - Decision: **APPROVED**.

19. **First quantity-company business profile**
    - Business: mobile-phone wholesaler.
    - Products: electronic gadgets, mobile phones, accessories, and gaming
      consoles.
    - Expected inventory scale: approximately 100,000 physical units distributed
      across multiple warehouses.
    - Activity: approximately 100 invoices per day and 30–40 other transactions
      per day.
    - Returns are low relative to invoices.
    - Required reports: daily sales, month-end profit, expenses, purchases, and
      stock.
    - Decision: **BUSINESS PROFILE AND SCALE MEANING RECORDED**.

20. **Rollout strategy**
    - Recommended: existing three companies remain serial-based; launch the
      first quantity company as a new pilot tenant after staging acceptance,
      then observe it before onboarding additional quantity companies.
    - Decision: **APPROVED — retain all existing companies as serial-based and
      introduce a new quantity company as the pilot tenant**.

## [x] DONE (2026-07-06): Write detailed document-attachment tests

Added `tests/suite/test_attachments.py` and wired it into `tests/suite/run_all.py`.
The module creates real tenant business documents, uses Django's real test
client with tenant middleware, isolates private media under a temp directory,
and covers sale, purchase, sale return, purchase return, payment, receipt, and
contra attachment flows.

Coverage includes one image + one PDF uploads, one-file-per-kind replacement,
preserving the unselected file kind during update, authenticated
metadata/preview/download endpoints, invalid file type/size validation, cleanup
after successful document delete, no cleanup after failed business delete,
attachment-only update bypass for sale/purchase/returns, and validation proving
payments/receipts/contra do not use that bypass.

Verification: in-memory Python syntax check passed;
`docker compose -f deploy/docker-compose.yml exec web python tests/suite/test_attachments.py`
passed 208/208 attachment checks; full
`docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py`
passed all modules.

---

## [x] DONE (2026-07-03): Port the cash-party feature to `tenant_company_1`

Completed by `tenancy/sql/fix_cash_party_port.sql` (idempotent; applied to all
tenants via `apply_sql_all_tenants`; folded into `tenant_template.sql`,
`production_hardening.sql`, and `build_multitenant_db.sql`; tenant schema
version bumped to **5**). Full write-up in `FIXED_ISSUES.md` →
"2026-07-03: Cash-Party Feature Ported to All Tenants".

Key findings from the port (vs. the risk analysis below, kept for history):

- The feared function-redefinition conflict **did not exist**: no integrity
  patch redefines the four `rebuild_*` journal builders or
  `detailed_ledger`/`detailed_ledger2` — the COGS-reflow fix only *calls*
  `rebuild_sales_journal`. Live `pg_get_functiondef` diffs proved
  `tenant_company_2`'s cash-aware bodies were byte-identical to
  `add_cash_transactions.sql` / `add_cash_party_ledger.sql` and already passed
  every integrity test alongside the guards. The "merge" reduced to applying
  those exact bodies.
- The gap was **worse than a misclassification**: `sale/views.py` and
  `purchase/views.py` call `get_cash_party_id(...)` / read `is_cash`
  unconditionally, so cash sales/purchases *errored* on `tenant_company_1`.
- A second drift layer surfaced during verification: the **invoice-description
  feature** (`description` columns on the four document tables +
  description-aware `get_current_*` fetchers from
  `add_invoice_description.sql`) was also missing on `tenant_company_1`, and
  the cash-aware ledger functions read those columns. It is included in the
  port patch as a prerequisite.
- `tests/suite/test_sales.py` now asserts the cash path **unconditionally**
  (feature-detection branch removed) plus sentinel-party seeding and
  `get_cash_party_id` resolution.

Verification (all green, 2026-07-03): `tests/suite/run_all.py` — ALL MODULES
PASSED (30/30 sales and 60/60 reports on *both* tenants; 70/70 HTTP);
`tests/test_transaction_lifecycle_deep.py` — all deep lifecycle checks passed
on both tenants; updated `tenant_template.sql` builds cleanly in a throwaway
schema; updated `production_hardening.sql` reruns cleanly on both tenants;
both tenants at `tenant_schema_version = 5` with both cash parties seeded.

<details>
<summary>Historical risk analysis (pre-port, superseded)</summary>

The original deferral reasoning: blindly replaying `add_cash_transactions.sql`
was believed dangerous because it does `CREATE OR REPLACE` on
`rebuild_sales_journal` etc., and the COGS-reflow fix in
`fix_transaction_integrity_guards.sql` depends on the current
`rebuild_sales_journal`. The planned mitigation was a hand-merged migration.
Live inspection showed the integrity patches never touch those functions, so
the patch bodies themselves were already the correct "merged" versions.

</details>
