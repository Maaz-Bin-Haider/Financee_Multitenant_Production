# Quantity-Based Company Architecture and Data-Model Design

**Phase:** 2 — Architecture and Schema-Family Design  
**Status:** Design baseline  
**Version:** 1.0  
**Date:** 2026-07-25  
**Requirements:** `SRS_QUANTITY_BASED_COMPANY.md`  
**Execution plan:** `IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`  
**Baseline evidence:** `tests/PHASE1_BASELINE_RESULTS.md`

---

## 1. Purpose

This document defines how Financee will support two independent tenant schema
families:

- Existing serial-number-based companies.
- New quantity-based companies.

It is a design contract for Phases 3–22. It does not create database objects,
change current company records, or enable quantity provisioning.

The design prioritizes:

- Zero regression to current serial companies.
- Trusted and immutable schema-family selection.
- PostgreSQL-owned business and accounting logic.
- Deterministic FIFO and exact historical replay.
- Safe concurrent stock consumption.
- Clear separation between shared HTTP behavior and inventory-mode behavior.
- Backward-compatible deployment and rollback.
- Testability and requirement traceability.

---

## 2. Architectural Decisions

### AD-001 — Two schema families, not one conditional business schema

Serial and quantity companies use separate SQL templates, hardening scripts,
versions, capability definitions, and inventory functions.

Reason:

- Their stock identities are fundamentally different.
- Serial stock tracks individual `PurchaseUnits` and `SoldUnits`.
- Quantity stock tracks aggregate quantities, FIFO layers, allocations, and
  warehouses.
- Mixing both in one schema would increase accidental cross-mode queries and
  make future migrations harder to reason about.

### AD-002 — Shared public control plane

Authentication, sessions, permissions, companies, memberships, subscriptions,
billing settings, subscription email logs, and the currency catalogue remain in
`public`.

The public `Company.inventory_mode` is the trusted schema-family selector.

### AD-003 — Business logic stays in PostgreSQL

Django validates transport-level input, permissions, and user experience. It
calls schema-relative stored functions for:

- Posting.
- Validation.
- FIFO allocation.
- Stock locking.
- Rebuild/replay.
- Accounting.
- Reports.

Python shall not independently calculate authoritative stock, FIFO COGS, tax,
discount, exchange gain/loss, or journal entries.

### AD-004 — Company type is immutable

`inventory_mode` becomes immutable once the company schema is provisioned.
A future conversion is a separate migration/export/import project.

### AD-005 — Family verification before activation

The public company row and tenant-local schema metadata must agree. A mismatch
causes a safe denial and operational alert; it never falls back to another
family.

### AD-006 — Expand-and-contract database evolution

New database versions add compatible objects/columns/functions first.
Destructive removal or signature replacement is deferred until the previous
application image is outside the rollback window.

### AD-007 — Append-first inventory history

Posted stock movements and FIFO allocations are durable facts. Corrections use
controlled rebuild/reversal semantics and preserve audit linkage rather than
silently rewriting unrelated history.

---

## 3. Component Architecture

```text
Browser
  |
  v
Django routes/templates/JSON views
  |
  +-- authentication / CSRF / permissions / feature flags / subscription
  |
  v
TenantSchemaMiddleware
  |
  +-- membership -> public Company
  +-- validate inventory_mode
  +-- SET search_path tenant, public
  +-- verify tenant_schema_metadata.family/version
  |
  v
Schema Family Registry
  |
  +------------------------------+
  |                              |
  v                              v
Serial capability              Quantity capability
existing views/SQL             quantity service contracts
  |                              |
  v                              v
Serial tenant schema           Quantity tenant schema
individual serial units        SKU/warehouse/FIFO quantities
```

Shared layers:

- Authentication and tenancy.
- Admin and company control.
- Subscriptions.
- Permissions.
- Feature flags.
- Attachment storage/access.
- Alerts and visual theme.
- Deployment and monitoring.

Separated layers:

- Inventory payloads.
- Inventory stored functions.
- Stock tables and views.
- Mode-specific reports.
- Mode-specific UI controls.

---

## 4. Schema-Family Registry

### 4.1 Responsibility

A central Python registry will describe supported schema families. Views,
provisioning, middleware, management commands, report navigation, and feature
availability shall query this registry rather than duplicate string conditions.

### 4.2 Proposed module

`tenancy/schema_families.py`

### 4.3 Logical contract

```python
@dataclass(frozen=True)
class SchemaFamily:
    key: str
    display_name: str
    template_path: str
    hardening_path: str
    required_version_setting: str
    capability_module: str
    supported_feature_keys: frozenset[str]
    unsupported_route_names: frozenset[str]

SCHEMA_FAMILIES = {
    "serial": SchemaFamily(...),
    "quantity": SchemaFamily(...),
}
```

Required registry operations:

- `get_schema_family(key)`
- `family_for_company(company)`
- `required_schema_version(family)`
- `template_for_family(family)`
- `hardening_for_family(family)`
- `capabilities_for_family(family)`
- `feature_supported(family, feature_key)`

Unknown family keys must raise a controlled configuration error.

### 4.4 Provisioning artifacts

Serial:

- `tenancy/sql/tenant_template.sql`
- `tenancy/sql/production_hardening.sql`
- `tenancy/sql/tenant_indexes.sql`

Quantity:

- `tenancy/sql/quantity/tenant_template.sql`
- `tenancy/sql/quantity/production_hardening.sql`
- `tenancy/sql/quantity/tenant_indexes.sql`
- `tenancy/sql/quantity/patches/*.sql`

Names may be adjusted during implementation, but family separation must remain.

### 4.5 Management command behavior

Existing commands shall retain serial compatibility.

New/family-aware commands:

- Provision company using its trusted public family.
- Apply SQL to all tenants of one family.
- Dry-run and `--only` selection.
- Reject a file/family mismatch.
- Print tenant, company, family, current version, target version, and outcome.
- Always reset `search_path`.

---

## 5. Public Schema Design

### 5.1 Company additions

Proposed fields:

| Field | Type | Rules |
|---|---|---|
| `inventory_mode` | short string/choices | `serial` or `quantity`; existing rows backfilled `serial`; immutable after provisioning |
| `base_currency` | FK to currency catalogue | required for new companies; safe backfill/default strategy for existing serial companies |
| `tax_environment` | short string/choices | `tax` or `non_tax`; required for quantity companies |
| `provisioning_state` | short string/choices | `pending`, `provisioning`, `ready`, `failed`; recommended for atomic operational clarity |
| `provisioning_error_code` | short string/nullable | sanitized operator-visible failure category; no secrets/SQL |

`schema_name` remains generated from the company primary key and validated by
existing helpers.

### 5.2 Currency catalogue

Logical fields:

| Field | Type | Rules |
|---|---|---|
| `code` | char(3) | ISO-style uppercase unique code |
| `name` | string | required |
| `symbol` | string | may repeat across currencies |
| `minor_units` | small integer | monetary display/storage rounding scale |
| `is_active` | boolean | disabled currencies unavailable for new companies |

Seed operation is idempotent.

### 5.3 Company immutability

Application validation:

- Admin disables type after provisioning.
- Model validation rejects changed mode.
- Base currency is locked after financial activity.

Database/business verification:

- Tenant schema stores family and base currency snapshot.
- Middleware verifies family.
- Financial posting verifies tenant base currency.

The public schema cannot use a simple database trigger to inspect arbitrary
tenant transaction state safely; tenant-local metadata/activity checks will be
called through a controlled service before admin updates.

### 5.4 Migration sequence

1. Add nullable/default-compatible fields.
2. Backfill all existing companies to `serial`.
3. Backfill a documented base currency without changing existing stored
   accounting values.
4. Add constraints after data verification.
5. Deploy code that understands both old transitional and final state.
6. Only then enable quantity selection.

No existing tenant schema is modified by the public migration.

---

## 6. Tenant Schema Metadata

Replace/extend the current singleton version concept for quantity tenants with:

`tenant_schema_metadata`

| Column | Type | Rule |
|---|---|---|
| `id` | boolean | singleton, always true |
| `family` | text | must equal `quantity` |
| `version` | integer | monotonically non-decreasing |
| `base_currency_code` | char(3) | agrees with public company |
| `created_at` | timestamptz | provisioning time |
| `applied_at` | timestamptz | last successful patch |

Serial schemas continue using current `tenant_schema_version` initially.
Serial metadata unification may occur only through an independently tested
backward-compatible patch.

Activation checks:

1. Schema exists.
2. Metadata table exists.
3. Family equals public company mode.
4. Version meets family requirement.
5. Base currency agrees where required.

---

## 7. Logical Quantity Data Model

### 7.1 Domain overview

```text
Company (public)
  |
  +-- Quantity Tenant Schema
        |
        +-- Products -> Variants/SKUs -> Unit
        +-- Warehouses
        +-- Parties
        +-- Purchases -> Purchase Lines -> FIFO Layers
        +-- Sales -> Sale Lines -> FIFO Allocations
        +-- Sale Returns -> Return Lines -> Allocation Reversals
        +-- Purchase Returns -> Return Lines -> Source Eligibility
        +-- Transfers -> Transfer Lines -> Layer Moves
        +-- Counts -> Count Lines -> Adjustments
        +-- Stock Movements
        +-- Journals -> Journal Lines -> Accounts/Parties
        +-- Payments/Receipts -> Invoice Allocations
        +-- Taxes / Document Sequences / Attachments / Audit
```

### 7.2 Master entities

#### `units_of_measure`

| Column | Notes |
|---|---|
| `unit_id` | primary key |
| `code` | unique: `PCS`, `BOX`, `KG`, `GM`, `LTR`, `MTR` |
| `name` | display name |
| `quantity_scale` | 0 for Piece/Box, 3 for measurement units |
| `is_active` | prevents new use without deleting history |

#### `products`

Parent descriptive identity:

- `product_id`
- `product_name`
- `category`
- `description`
- `is_active`
- timestamps/user attribution

#### `product_variants`

Sellable SKU identity:

- `variant_id`
- `product_id`
- `sku`
- `brand`
- `model`
- `color`
- `storage`
- `ram`
- `region`
- `condition`
- `unit_id`
- `reorder_level`
- `is_active`
- timestamps/user attribution

Constraints:

- Tenant-unique normalized SKU.
- Tenant-unique normalized sellable combination.
- Unit cannot change after referenced movement.
- Variant identifying fields cannot create a duplicate.

Empty/non-applicable variant attributes use normalized empty values or nullable
columns under one documented uniqueness strategy. SQL must prevent `NULL`
semantics from allowing duplicate combinations.

#### `warehouses`

- `warehouse_id`
- `code`
- `name`
- `address`
- `is_default`
- `is_active`
- timestamps/user attribution

Only one active default warehouse.

#### `parties`

Preserve current party semantics:

- Customer.
- Vendor.
- Both.
- Expense.
- Cash sentinel parties.
- Opening balances.
- Account associations.

### 7.3 Accounting entities

#### `chart_of_accounts`

Logical parity with current chart plus:

- Input/output tax accounts as configured.
- Inventory adjustment gain/loss.
- Realized exchange gain.
- Realized exchange loss.

#### `journal_entries`

- immutable/display document linkage
- entry date
- description
- source document type/ID/number
- created by/time
- reversal linkage/status

#### `journal_lines`

- journal
- account
- optional party
- debit
- credit
- base currency only
- constraints: non-negative; exactly one of debit/credit positive

Foreign amounts are document/allocation metadata; the general ledger remains
in company base currency.

### 7.4 Document base concepts

Every business document has:

- Internal primary key.
- User-facing number.
- Business date.
- Status.
- Description.
- Created/updated user/time.
- Base currency.
- Optional transaction currency.
- Optional exchange rate.
- Foreign/base totals where applicable.
- Reversal/original linkage.
- Journal linkage where financial.

Status vocabulary:

- `draft` is optional only if fully implemented; unposted drafts have no stock
  or journal effects.
- `posted` is active authoritative state.
- `reversed` preserves history and has compensating effects.
- `void` is reserved for never-posted/cancelled number reservations.

The first release may post directly without drafts. Posted documents must never
be represented as deleted if audit/history requires preservation.

---

## 8. Inventory Entities

### 8.1 `stock_movements`

Purpose: immutable chronological quantity ledger.

Columns:

- `movement_id`
- `variant_id`
- `warehouse_id`
- `movement_date`
- `effective_at` or deterministic ordering key
- `movement_type`
- `quantity_in`
- `quantity_out`
- `source_type`
- `source_id`
- `source_line_id`
- `document_number`
- `unit_cost_base` when applicable
- `total_cost_base` when applicable
- `created_by`
- `created_at`
- `reversal_of_movement_id`

Constraints:

- Exactly one direction is positive.
- Quantity respects SKU unit precision.
- Positive values only.
- Source identity is unique for non-split movements as designed.
- No direct application insert outside controlled functions.

Movement types:

- Opening.
- Purchase.
- Sale.
- Sale return.
- Purchase return.
- Transfer out.
- Transfer in.
- Positive adjustment.
- Negative adjustment.
- Reversal types or reversal linkage.

### 8.2 `fifo_layers`

Purpose: track remaining costed inbound quantity.

Columns:

- `layer_id`
- `variant_id`
- `warehouse_id`
- `source_type`
- `source_id`
- `source_line_id`
- `source_date`
- `sequence_key`
- `original_quantity`
- `remaining_quantity`
- `unit_cost_base`
- `created_at`
- `restored_from_allocation_id` where applicable

Layer order:

1. Business/source date.
2. Stable effective ordering value.
3. Layer primary key.

Relying only on date is insufficient because same-day order must be
deterministic.

### 8.3 `fifo_allocations`

Purpose: durable link between outbound quantity and consumed layers.

Columns:

- `allocation_id`
- `outbound_type`
- `outbound_id`
- `outbound_line_id`
- `layer_id`
- `quantity`
- `unit_cost_base`
- `total_cost_base`
- `allocation_order`
- `created_at`
- reversal/restoration metadata

Unique/consistency rules:

- Sum of allocations for a sale line equals sale quantity.
- Allocation quantity never exceeds layer availability at posting.
- Stored cost never changes silently.

### 8.4 Stock balance

Stock balance shall be derived or maintained from movements with reconciliation.
Recommended:

- Authoritative movement/FIFO history.
- Optional `stock_balances` projection for fast reads:
  - variant
  - warehouse
  - on-hand quantity
  - updated version/time

If a projection table is used, database functions update it atomically and
reconciliation tests prove equality with movements and FIFO.

---

## 9. Transaction Data Model

### 9.1 Purchases

`purchase_invoices`

- vendor
- warehouse
- document number/date/status
- currencies/rate
- subtotal/discount/tax/total in foreign and base values
- journal
- description/audit

`purchase_lines`

- invoice
- variant/SKU
- quantity
- unit cost
- line discount
- invoice discount allocation
- taxable value
- tax code/rate/mode/amount
- base/foreign totals

Posting creates:

- Purchase movement.
- FIFO layer.
- Inventory debit.
- AP or Cash/Bank credit.
- Tax lines as configured.

### 9.2 Sales

`sales_invoices` and `sales_lines` mirror relevant purchase document fields.

Posting creates:

- Sale movement.
- FIFO allocations.
- AR or Cash/Bank debit.
- Revenue credit.
- Tax liability lines.
- COGS debit.
- Inventory credit.

### 9.3 Sale returns

`sale_returns`

- customer
- destination warehouse
- source-aware lines
- financial totals

`sale_return_lines`

- original sale line
- variant
- quantity
- original revenue/tax/discount allocation snapshot
- returnable balance

Return cost is restored from exact original FIFO allocations. If returned
quantity spans multiple original allocations, restoration follows the
allocation order associated with the returned portion under a documented
deterministic rule.

### 9.4 Purchase returns

`purchase_returns` / `purchase_return_lines`

- original purchase line.
- source warehouse.
- quantity.
- original unit cost/tax/discount basis.

Eligibility must establish that enough quantity attributable to the source
purchase remains returnable. A source-allocation ledger may be required in
addition to FIFO layers because transfers and sale returns move/restore cost.

### 9.5 Transfers

`warehouse_transfers` / `warehouse_transfer_lines`

- source/destination.
- variant and quantity.
- status/number/date.

Transfer consumes source FIFO layers and creates destination layers retaining:

- Original economic cost.
- Link to source layer.
- Transfer lineage.

No P&L or party journal.

### 9.6 Counts and adjustments

`physical_counts`

- warehouse.
- count date/cutoff.
- status: open, submitted, approved, posted, cancelled.
- number/user/timestamps.

`physical_count_lines`

- variant.
- system quantity at cutoff.
- counted quantity.
- variance.
- reason/note.

`inventory_adjustments` / lines

- source physical count or manual authorized adjustment.
- positive/negative direction.
- reason.
- approval.
- FIFO/accounting valuation.

---

## 10. Tax Model

### 10.1 `tax_codes`

- `tax_code_id`
- code/name.
- rate.
- classification support.
- purchase control account.
- sale control account.
- active/date metadata.

Tax configurations may change for future documents. Posted line snapshots do
not refer to live rate values for historical recalculation.

### 10.2 Calculation contract

For each line:

1. `gross = quantity × unit_price`
2. Apply line discount.
3. Allocate invoice-level discount proportionally using a deterministic
   remainder rule.
4. Calculate taxable value.
5. For exclusive tax: `tax = taxable_value × rate`.
6. For inclusive tax: extract tax from the discounted inclusive amount.
7. Apply currency/money rounding.
8. Store inputs and results.

Invoice discount remainder is assigned deterministically, for example to the
largest eligible line then stable line order, so line totals equal invoice
totals exactly.

Tax classifications:

- Taxable.
- Zero-rated.
- Exempt with optional reference.

Non-tax companies:

- No tax code required.
- Tax amounts must be zero.
- Tax journal lines prohibited.

---

## 11. Currency Model

### 11.1 Principles

- General ledger uses base currency.
- A foreign document stores both foreign and base values.
- Rates use fixed precision, proposed `numeric(20, 10)`.
- Rates are positive.
- Base-currency documents use an effective rate of 1 internally but do not ask
  users for it.

### 11.2 Payment/receipt allocations

Add allocation entities:

- `payment_allocations`
- `receipt_allocations`

Each allocation stores:

- Payment/receipt.
- Invoice.
- Foreign amount settled.
- Invoice-rate base carrying value.
- Settlement rate.
- Settlement base amount.
- Realized gain/loss.

### 11.3 Realized result

Supplier payment:

`realized_difference = settlement_base_cash - invoice_base_liability_released`

- Positive difference: exchange loss.
- Negative difference: exchange gain.

Customer receipt:

`realized_difference = settlement_base_cash - invoice_base_receivable_released`

- Positive difference: exchange gain.
- Negative difference: exchange loss.

Partial settlement releases carrying value proportionally from the remaining
foreign balance using stored invoice allocation values.

No month-end unrealized revaluation function or journal is designed for V1.

---

## 12. Document Numbering

### 12.1 `document_sequences`

| Column | Notes |
|---|---|
| `document_type` | primary-key component |
| `prefix` | `SAL`, `PUR`, etc. |
| `padding` | default 6 |
| `updated_at` | audit |

Number allocation:

1. Read the next value from the document type's PostgreSQL sequence.
2. Format prefix and padded value using `document_sequence_config`.
3. Store the resulting number on the document.

PostgreSQL sequences shall be used because they are concurrency-safe,
non-transactional, allow gaps, and do not reuse a value after a rolled-back
document attempt. External retries/idempotency still prevent duplicate business
documents.

User-facing number is unique per tenant and document type.

---

## 13. Document Lifecycle and Mutation Rules

### 13.1 Posting

Posting is one database transaction:

1. Validate party, warehouse, SKU, unit precision, period, tax, discount,
   currency, rate, permissions context, and idempotency token.
2. Acquire locks in canonical order.
3. Validate stock/source eligibility.
4. Allocate document number if needed.
5. Insert document and lines.
6. Create movements/layers/allocations.
7. Create balanced journal.
8. Reconcile critical local invariants.
9. Commit.

### 13.2 Editing

Approved posted documents are editable only through controlled replacement:

1. Identify dependency closure from the edited effective date forward for
   affected SKU/warehouses and financial documents.
2. Lock affected partition/resources.
3. Reject if closed period or unsupported dependency exists.
4. Save original audit snapshot.
5. Remove/reverse derived movements, allocations, layers, and journals inside
   the transaction.
6. Apply new document values.
7. Replay affected timeline deterministically.
8. Verify no historical negative stock.
9. Verify returns and settlements remain within source values.
10. Verify journals and reconciliations.
11. Commit or fully roll back.

### 13.3 Deletion versus reversal

Recommended final behavior:

- Unposted draft: may be deleted.
- Posted document with no dependent history: may use controlled reversal/void
  while retaining number/audit.
- Posted document with dependencies: edit/reversal only if replay proves safe.
- Closed-period document: no mutation except approved close-reversal process.

Existing serial delete behavior remains unchanged.

---

## 14. FIFO Algorithm

### 14.1 Normal outbound allocation

Input:

- variant.
- warehouse.
- quantity.
- effective ordering key.

Algorithm:

1. Validate positive quantity and SKU precision.
2. Acquire variant/warehouse advisory or balance-row lock.
3. Select eligible FIFO layers:
   - same variant/warehouse.
   - effective before/equal outbound.
   - remaining quantity > 0.
   - ordered by source date, sequence key, layer ID.
   - `FOR UPDATE`.
4. Sum availability.
5. If insufficient, raise controlled error with requested/available.
6. Consume layers in order.
7. Insert one allocation per consumed layer.
8. Reduce remaining quantities.
9. Insert stock movement.
10. Return total COGS and allocation details.

### 14.2 Sale return restoration

1. Lock original sale line and its allocations.
2. Calculate remaining returnable quantity.
3. Reject excessive cumulative return.
4. Select the exact original allocation portions associated with the returned
   quantity using deterministic allocation order.
5. Create restoration layer(s) at destination warehouse with original costs
   and lineage.
6. Insert return movement and accounting reversal.

This does not recompute return cost using current FIFO cost.

### 14.3 Purchase return eligibility

Purchase return must not simply consume arbitrary current FIFO:

1. Lock original purchase line/layers and relevant lineage.
2. Determine quantity from that source still economically available after
   sales, transfers, prior returns, sale returns, and adjustments.
3. Reject quantity exceeding source-eligible amount.
4. Remove/consume at original purchase cost.
5. Record source linkage.

Phase 9 prototypes must prove the lineage representation supports this before
purchase-return implementation begins.

---

## 15. Backdated Replay

### 15.1 Replay scope

Replay is scoped by affected:

- Variant(s).
- Warehouse(s), including transfer-connected warehouses.
- Effective date/time onward.
- Documents whose allocations or journals depend on affected costs.

### 15.2 Deterministic event ordering

Order by:

1. Business date.
2. Document effective sequence/time.
3. Document-type precedence only if explicitly required.
4. Stable document/line primary key.

User-facing date alone cannot determine FIFO order.

### 15.3 Replay algorithm

1. Acquire a transaction-scoped advisory lock per tenant plus ordered
   variant/warehouse locks for the affected scope.
2. Reject closed-period intersection.
3. Load affected event timeline.
4. Save audit change set.
5. Reset derived allocations/layer remainders/movement projections within
   scope.
6. Replay inbound/outbound events chronologically.
7. Stop and roll back at first insufficient historical stock.
8. Rebuild affected COGS and journals.
9. Revalidate return/settlement limits.
10. Reconcile closing stock, FIFO value, Inventory account, and trial balance.

### 15.4 Complexity guard

Very large replay scopes may exceed synchronous request limits. The first
release may:

- Block edits whose dependency closure exceeds an approved threshold.
- Require operator maintenance tooling.

It shall not partially apply a timed-out replay.

---

## 16. Concurrency and Lock Ordering

### 16.1 Canonical lock order

To reduce deadlocks:

1. Tenant-level replay/advisory lock when doing backdated rebuild.
2. Period-close row.
3. Warehouse IDs ascending.
4. Variant IDs ascending.
5. Stock balance rows `(warehouse_id, variant_id)` ascending.
6. FIFO layer IDs ascending.
7. Source document/header then line IDs ascending.
8. Document sequence.
9. Journal/account resources where necessary.

Every function touching multiple items/warehouses must sort inputs before
locking.

### 16.2 Normal sales

Normal current-date sales lock only affected balance/layer rows, not the entire
tenant.

### 16.3 Transfers

Always lock lower warehouse ID first regardless of transfer direction, then
variant order.

### 16.4 Returns

Lock source document/line, returnable aggregate, then FIFO lineage in stable
order.

### 16.5 Retry policy

PostgreSQL serialization/deadlock errors may be retried by a bounded service
policy only when the request has an idempotency key. Arbitrary retries without
idempotency are prohibited.

---

## 17. Idempotency

Every create/post endpoint receives a client-generated UUID idempotency key.

Tenant table:

`idempotency_requests`

- key.
- operation type.
- user.
- request hash.
- status.
- resulting document ID/number.
- created/expiry time.

Rules:

- Same key and same request returns the original result.
- Same key and different request is rejected.
- In-progress duplicate waits or receives a controlled conflict.
- Failed transaction does not expose a partially created document.

Updates use optimistic document version plus idempotency key.

---

## 18. Precision and Rounding

Proposed PostgreSQL types:

| Value | Type |
|---|---|
| Quantity | `numeric(18,3)` |
| Unit price/cost foreign/base | `numeric(20,6)` |
| Document monetary totals | `numeric(24,4)` base storage |
| Tax/discount rate | `numeric(9,6)` |
| Exchange rate | `numeric(20,10)` |
| FIFO total cost | `numeric(24,6)` internally |

Rules:

- No floating point.
- Quantity precision validated from unit.
- Line intermediate calculations retain higher precision.
- Monetary rounding occurs at documented line stages.
- Invoice totals equal exact sum of stored line results.
- Journal base amounts match document base totals.
- FIFO allocation rounding remainder is assigned deterministically to the final
  allocation so total COGS equals the source cost represented.
- Currency minor units control display and finalized foreign-document scale.

Architecture decision:

- Ledger debit/credit and posted base totals use `numeric(24,4)`.
- Line/FIFO calculation intermediates use `numeric(24,6)`.
- Exchange rates use `numeric(20,10)`.
- Display and finalized foreign amounts round using the transaction currency's
  configured minor units.
- Any base-currency rounding remainder is posted through a documented rounding
  line/account only when non-zero; tests require invoice, journal, and report
  agreement.

---

## 19. Backend Capability Contracts

### 19.1 Proposed structure

```text
inventory/
  capabilities.py
  serial.py
  quantity.py
  payloads.py
```

Or equivalent modules within existing apps, provided selection remains central.

### 19.2 Capability interface

- `purchase_page_context`
- `parse_purchase_payload`
- `create_purchase`
- `get_purchase`
- `update_purchase`
- `delete_or_reverse_purchase`
- Equivalent sale/return methods.
- `supported_reports`
- `supported_features`
- `stock_lookup`

Shared Django views may call capability objects. SQL function names are fixed by
family configuration rather than browser values.

### 19.3 SQL naming

Quantity stored functions use explicit names during transition, for example:

- `qty_create_purchase`
- `qty_update_purchase`
- `qty_create_sale`
- `qty_create_sale_return`
- `qty_create_purchase_return`
- `qty_post_transfer`
- `qty_post_adjustment`

Because schemas are already separated, generic names could work; explicit
`qty_` names reduce accidental calls and aid logs/tests. The capability layer
hides the physical name.

### 19.4 Error contract

Stored functions raise categorized business errors without secrets.
Django maps categories to:

- 400 validation.
- 403 permission/tenant/feature/subscription.
- 409 conflict/concurrency/idempotency/dependency.
- 423 closed/locked period where appropriate.
- 500 sanitized unexpected error.

---

## 20. Payload Contracts

### 20.1 Quantity purchase line

```json
{
  "variant_id": 101,
  "warehouse_id": 3,
  "quantity": "25.000",
  "unit_price": "1250.00",
  "discount": {"type": "percent", "value": "2.5"},
  "tax_code": "ST18",
  "tax_classification": "taxable"
}
```

Warehouse may live at header level when all lines share it. If line-level
warehouses are allowed, header warehouse is omitted and every line requires one.
V1 recommendation: one warehouse per purchase/sale document for clearer
operations and accounting; transfers handle movement between warehouses.

### 20.2 Quantity sale line

Same identity fields; no serial array.

### 20.3 Return line

```json
{
  "source_line_id": 9001,
  "quantity": "5.000",
  "warehouse_id": 3
}
```

Client does not submit authoritative cost/tax reversal.

### 20.4 Foreign document header

```json
{
  "transaction_currency": "USD",
  "exchange_rate": "280.0000000000"
}
```

Base-currency document omits rate or supplies currency equal to base; server
normalizes rate to 1.

### 20.5 Version/idempotency

Create:

- `idempotency_key`

Update:

- `document_version`
- `idempotency_key`

---

## 21. Report Architecture and Reconciliation

### 21.1 Report catalogue

Central report metadata:

- report key.
- supported families.
- required permission.
- feature flag.
- route/API.
- export support.
- reconciliation source.

### 21.2 Source hierarchy

Reports use:

- Posted active documents.
- Stock movements/FIFO allocations.
- Journal lines.
- Stable views/materialized projections only when reconciled.

Reports must not infer current stock by incomplete document subsets.

### 21.3 Required reconciliations

| Report | Reconciliation |
|---|---|
| Trial balance | Sum debit equals sum credit |
| AR/AP | Party subledger equals control-account party lines |
| Stock summary | Movements equation equals balance projection |
| FIFO valuation | Remaining layers equal stock quantity/value |
| Inventory valuation | FIFO total equals Inventory GL balance, adjusted only by documented timing/status |
| Sales summary | Posted sales minus returns |
| COGS | Sale allocation costs minus restored return costs |
| Tax | Line tax snapshots equal tax-control journal lines |
| Realized FX | Settlement allocation differences equal FX journal accounts |
| Month profit | Revenue - returns - COGS - expenses +/- realized FX and adjustments |
| Transfers | Company quantity/value net zero |
| Counts | Posted variance equals adjustment movements/journals |

### 21.4 Serial-only reports

Report registry excludes serial ledger/detail endpoints for quantity companies.
Backend denies direct calls. Serial family registration remains unchanged.

---

## 22. Feature and Permission Design

New permission groups:

- Warehouse view/manage.
- Transfer view/create/update/reverse.
- Count view/create/submit/approve/post.
- Adjustment view/create/approve/reverse.
- Quantity stock reports.
- Quantity purchase reports.
- Tax configuration.
- Currency settlement.

Separation of duties:

- A configurable policy should prevent a count creator from approving their own
  adjustment where required.
- At minimum, approval uses a distinct permission even if the same user can hold
  both.

Feature registry:

- Shared features remain.
- Quantity reports are registered only for quantity family.
- Serial reports only for serial family.
- Unsupported feature keys are not silently treated as enabled.

---

## 23. Provisioning Transaction

Proposed company lifecycle:

1. Admin validates name, mode, base currency, tax environment.
2. Save public company as `pending`.
3. Generate schema name.
4. Set state `provisioning`.
5. Open database transaction/advisory provisioning lock.
6. Create schema and execute correct family template.
7. Validate metadata, version, required object fingerprint, seed accounts,
   units, cash parties, sequences, and default warehouse if configured.
8. Commit.
9. Mark company `ready`.

On failure:

- Roll back schema creation when transactional DDL permits.
- Otherwise drop only the validated newly created schema as compensation.
- Mark company `failed` with sanitized error code.
- Do not activate membership business routes.
- Retry is idempotent and operator-controlled.

Signal timing must avoid a public row appearing ready before the schema passes.
Implementation may replace the current simple post-save behavior with a
transaction-aware service called by admin/commands while preserving serial
creation compatibility.

---

## 24. Rollback Compatibility

### 24.1 Phase 3 public migration

Old application images do not know new fields. Additive nullable/default fields
are safe. Do not change required constructor behavior until new image is active.

### 24.2 Quantity objects

Old images never activate quantity companies because their views lack
capabilities. During rollout:

- Quantity selection stays feature-disabled until new code is verified.
- Existing serial companies keep current paths.

### 24.3 Function evolution

- Add new signature/version first.
- Deploy code using it.
- Keep old signature through rollback window.
- Remove only in a later version after audit.

### 24.4 Rollback after quantity pilot

- Disable pilot company access if the application rolls back to an image that
  cannot serve quantity mode.
- Do not reinterpret quantity schema as serial.
- Existing serial companies remain available.
- Retain pilot data for forward recovery.

---

## 25. Threat and Failure Review

| Threat/failure | Design control |
|---|---|
| Browser sends `quantity` for serial company | Ignore browser family; trusted Company/registry |
| Public type and schema mismatch | Activation denial and alert |
| Concurrent final-stock sales | Ordered balance/layer row locks |
| Duplicate submit | Idempotency table/key |
| Return exceeds source | Locked cumulative source calculation |
| Backdated edit creates historical negative stock | Deterministic replay and full rollback |
| Transfer deadlock | Warehouse/variant canonical lock order |
| Tax configuration changes history | Store line snapshots |
| Exchange-rate change alters invoice | Store applied rate/base values |
| Partial payment misstates FX | Explicit invoice allocation |
| Old image after DB upgrade | Expand-and-contract compatibility |
| Wrong hardening file applied | Family-aware command verifies metadata |
| Report totals drift | Mandatory source/GL reconciliations |
| Connection leaks tenant path | Existing reset plus concurrency tests |
| Large replay times out | Scope threshold; no partial commit |

---

## 26. Design Walkthroughs

### 26.1 Domestic FIFO lifecycle

1. Purchase 100 units at 100 into A → layer A1 100@100.
2. Purchase 50 at 120 → layer A2 50@120.
3. Transfer 40 to B → consume A1; create B lineage 40@100.
4. Sell 70 from A → consume remaining A1 60@100 + A2 10@120.
5. COGS = 7,200; A remains 40@120; B remains 40@100.
6. Return 5 from sale → restore exact allocation portion according to
   deterministic sale-allocation return rule, not current 120 cost.
7. Reconcile movements, layers, Inventory, COGS, and trial balance.

Design outcome: supported.

### 26.2 Excessive concurrent sale

- Stock: 10.
- Request X sells 8; request Y sells 8 simultaneously.
- Both lock same balance/layers in order.
- One commits; second sees 2 and is rejected.

Design outcome: no negative stock.

### 26.3 Backdated purchase

- Day 2 sale previously consumed available layers.
- Day 1 purchase inserted.
- Replay locks affected SKU/warehouse and reallocates Day 2 sale FIFO.
- COGS/journal rebuild follows.
- If any historical point remains negative, entire edit rolls back.

Design outcome: supported with replay.

### 26.4 Sale return then resale

- Return locks source allocation and remaining returnable amount.
- Restores original cost layer.
- Resale consumes according to FIFO effective order.
- Second excessive return is rejected.

Design outcome: supported.

### 26.5 Foreign supplier partial payment

- USD 1,000 invoice at PKR 280 = PKR 280,000 AP.
- Pay USD 400 at PKR 285:
  - Release PKR 112,000 liability.
  - Credit bank PKR 114,000.
  - Debit exchange loss PKR 2,000.
  - Remaining foreign AP USD 600 carrying PKR 168,000.
- Later settlement calculates only remaining amount.

Design outcome: supported; no unrealized revaluation.

### 26.6 Closed month edit

- User edits purchase dated inside closed period.
- Period lock/validation occurs before rebuild.
- Operation rejected without mutation.

Design outcome: supported.

---

## 27. Phase-to-Component Map

| Implementation phase | Primary design components |
|---:|---|
| 3 | Public Company metadata, migrations, immutability |
| 4 | Currency catalogue, base currency, tax environment |
| 5 | Registry, provisioning, quantity metadata/template |
| 6 | Accounts, journals, sequences |
| 7 | Products, variants, SKU, units |
| 8 | Warehouses |
| 9 | Movements, FIFO layers/allocations, locks/replay |
| 10 | Opening stock |
| 11–14 | Purchases, sales, returns |
| 15 | Transfers and layer lineage |
| 16 | Counts/adjustments |
| 17 | Tax/discount snapshots/calculations |
| 18 | Currency documents and settlement allocations |
| 19 | Shared finance and close |
| 20 | Attachments, audit, permissions, features |
| 21 | Capability dispatch and UI payloads |
| 22 | Reports/reconciliation |

---

## 28. Engineering Decisions to Validate During Implementation

These decisions do not reopen approved product behavior. Their physical
implementation must be prototyped and tested in the named phase:

1. Monetary precision uses the fixed scales in Section 18 — validate in
   Phases 4, 6, 17, and 18.
2. User-facing numbers use PostgreSQL sequences plus formatting configuration —
   validate concurrency/no-reuse in Phase 6.
3. Variant uniqueness uses normalized generated columns or equivalent
   expression indexes with null-safe values — finalize physical SQL in Phase 7.
4. `stock_balances` is an atomically maintained projection table; movements and
   FIFO remain the reconcilable authority — validate in Phase 9.
5. Purchase-source lineage is retained through FIFO layer parent/source links
   and allocation/restoration records — prove purchase-return eligibility in
   Phase 9 before Phase 14.
6. Replay is synchronous only within a measured safe scope; oversized replay is
   blocked for controlled operator handling — set the threshold from Phase 26
   evidence.
7. V1 uses one warehouse per purchase/sale document; multi-warehouse invoices
   are split into separate documents. Returns specify warehouse explicitly.
8. Draft documents are deferred. V1 posts directly and preserves corrections
   through guarded update/reversal.
9. Financial/inventory audit is an append-only tenant table; shared admin and
   security events may additionally use a public operational audit table.

Each decision requires tests and documentation before its dependent phase exits.

---

## 29. Phase 2 Exit Criteria

Phase 2 passes when:

- Schema-family registry and provisioning design are complete.
- Public migration/backfill/immutability design is complete.
- Logical data model covers all SRS entities.
- FIFO, return restoration, purchase-return eligibility, replay, lock order,
  idempotency, and document lifecycle are defined.
- Precision and rounding responsibilities are defined.
- Payload and backend capability contracts are defined.
- Report reconciliation sources are defined.
- Rollback compatibility is defined.
- SRS requirements are mapped to components and tests.
- Design walkthroughs show no unresolved product contradiction.
- Documentation formatting and cross-links pass.
