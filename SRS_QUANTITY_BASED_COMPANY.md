# Software Requirements Specification
## Financee Quantity-Based Company

**Document status:** Approved requirements baseline for architecture and development  
**Version:** 1.0  
**Date:** 2026-07-25  
**Related system:** Financee Multitenant Accounting and Inventory System  
**Primary references:** `README.md`, `PROJECT_CONTEXT.md`, `FIXED_ISSUES.md`,
`CLAUDE.md`, `todo.md`, the current source tree, tenant SQL, and test suites

**Implementation sequencing and rollout source of truth:**
`IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`. This SRS defines required
behavior; the implementation plan defines the 33 controlled phases, mandatory
tests after each phase, evidence, exit gates, staging, production rollout,
rollback, pilot, and observation process.

---

## 1. Purpose

This Software Requirements Specification (SRS) defines the complete
requirements for adding quantity-based companies to Financee while preserving
the existing serial-number-based system.

Financee currently identifies every inventory unit by a serial number. The
current serial workflow is working and is not to be replaced. This update adds
a second tenant schema family in which stock is managed as quantities by item,
variant, and warehouse. Quantity companies will not enter or track serial
numbers during purchases, sales, purchase returns, or sale returns.

The document is intended to:

- Establish a single development and acceptance baseline.
- Separate existing serial-system behavior from new quantity requirements.
- Prevent accidental regressions in the serial system.
- Define the quantity data model, accounting behavior, reports, interfaces,
  tests, deployment controls, and operational requirements.
- Provide traceability from each requirement to its origin.
- Identify exclusions and decisions that must not be silently changed during
  implementation.

This document specifies required behavior. It does not itself authorize a live
production deployment.

---

## 2. Requirement Origin and Priority

Every requirement uses one or more origin labels:

| Label | Meaning |
|---|---|
| `SERIAL-PARITY` | Existing serial-company behavior that quantity companies must preserve semantically. |
| `SERIAL-ADAPTED` | Existing behavior whose inventory-specific implementation must be redesigned for quantities. |
| `SHARED-PLATFORM` | Existing public-schema, security, tenancy, subscription, admin, attachment, UI, or deployment capability shared by both company types. |
| `QUANTITY-NEW` | New behavior required only by quantity-based companies. |
| `OWNER-APPROVED` | A requirement explicitly approved during Phase 0 on 2026-07-25. |
| `ENGINEERING-MANDATORY` | A safeguard required to implement the approved behavior safely. |

Priorities:

| Priority | Meaning |
|---|---|
| `P0` | Release blocker. The system must not go live without it. |
| `P1` | Mandatory for the first supported quantity-company release. |
| `P2` | Beneficial follow-up explicitly outside the first release. |

Normative words have their usual meaning:

- **Must/shall:** mandatory.
- **Should:** recommended unless an approved exception exists.
- **May:** optional.

---

## 3. Scope

### 3.1 In Scope

- A company type selected during company creation:
  - Serial-based.
  - Quantity-based.
- Separate tenant schema families and schema versioning.
- Quantity inventory organized by item, variant, warehouse, and FIFO cost.
- Purchases, sales, sale returns, purchase returns, warehouse transfers,
  physical counts, and inventory adjustments without serial numbers.
- Existing double-entry accounting behavior.
- Multiple warehouses.
- Product variants and unique SKUs.
- Per-item units of measure without unit conversion.
- Taxes, discounts, tax/non-tax companies, and multi-currency transactions.
- Realized exchange gains and losses.
- Redesigned accounts, stock, sales, purchase, expense, and profitability
  reports.
- Shared permissions, subscriptions, attachments, descriptions, alerts,
  administration, and visual theme.
- Complete serial and quantity regression, accounting, concurrency,
  multitenancy, CI/CD, ARM64, and deployment verification.

### 3.2 Out of Scope for Version 1

- Converting an existing serial company into a quantity company.
- Changing a company type after provisioning.
- Batch, lot, or expiry-date inventory tracking.
- Serial numbers inside quantity-company inventory.
- Unit conversion, such as purchasing cartons and selling pieces from the same
  SKU.
- Month-end unrealized foreign-currency revaluation.
- Automatic internet exchange-rate feeds.
- Negative-stock overrides.
- A parent/child deployment that combines serial and quantity stock inside one
  company schema.
- Replacing or redesigning the existing serial schema.

### 3.3 Future-Compatible but Not Implemented

The first-release design should avoid preventing later additions of:

- Units-of-measure conversions.
- Batch, lot, and expiry tracking.
- Additional variant dimensions.
- Automated exchange-rate feeds.
- Unrealized exchange revaluation.
- Serial-to-quantity migration tooling.
- Additional warehouse hierarchy or bin locations.

---

## 4. System Context

Financee is a Django and PostgreSQL multitenant accounting and inventory
application.

- Django handles HTTP routing, authentication, authorization, request
  validation, tenant activation, templates, administration, and orchestration.
- PostgreSQL tenant schemas own accounting and inventory business logic through
  stored functions, triggers, constraints, and views.
- Shared authentication, sessions, permissions, companies, memberships,
  subscriptions, billing settings, and subscription email logs live in the
  `public` schema.
- Each company has one isolated PostgreSQL schema.
- Tenant middleware selects the current schema through a request-scoped
  `search_path` and resets it after every request.
- Docker runs PostgreSQL 16, Redis, Django/Gunicorn, and Nginx.
- Production uses a multi-architecture image on an ARM-based AWS EC2
  `t4g.medium`.

The quantity implementation shall follow this architecture. Business accounting
or inventory logic shall not be duplicated in Python when it belongs in tenant
SQL.

---

## 5. Stakeholders and User Roles

### 5.1 Stakeholders

- Product owner/system operator.
- Existing serial-company customers.
- New quantity-company customers.
- Company owners and administrators.
- Accountants.
- Purchasing staff.
- Sales staff.
- Warehouse/inventory staff.
- Auditors/read-only users.
- Developers and deployment operators.

### 5.2 Roles

The existing permission system remains authoritative. Quantity features shall
map to explicit permissions for:

- Company administration.
- Item and variant management.
- Warehouse management.
- Purchase entry and modification.
- Sale entry and modification.
- Purchase returns.
- Sale returns.
- Warehouse transfers.
- Physical counts and adjustments.
- Payments and receipts.
- Reports and exports.
- Month close and reversal.
- Attachment access.
- Audit access.

Users shall see and call only routes permitted by both their Django permissions
and their company’s enabled feature flags.

---

## 6. High-Level Product Requirements

### 6.1 Company Type

**FR-COMP-001 — Company type selection**  
Origin: `SHARED-PLATFORM`, `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

The custom admin company-creation form shall require selection of either
`Serial-based` or `Quantity-based`.

**FR-COMP-002 — Existing-company compatibility**  
Origin: `SERIAL-PARITY`, `OWNER-APPROVED`  
Priority: `P0`

All companies existing before this feature is deployed shall be migrated to
`Serial-based` without modifying their business schemas or workflows.

**FR-COMP-003 — Immutable company type**  
Origin: `OWNER-APPROVED`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Company type shall be immutable after tenant provisioning. Changing type shall
require a separate future migration project and shall not be supported by this
release.

**FR-COMP-004 — Trusted type source**  
Origin: `SHARED-PLATFORM`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Company type shall be read from the authenticated membership’s public
`Company` record. A request shall never choose its schema family from browser
input.

**FR-COMP-005 — Admin explanation and confirmation**  
Origin: `QUANTITY-NEW`  
Priority: `P1`

The company form shall explain both company types and warn that the selected
type cannot be changed after provisioning.

**FR-COMP-006 — Base currency selection**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Admin shall select a base currency from a worldwide currency catalogue while
creating a company. Base currency shall become immutable after the company has
financial transactions.

**FR-COMP-007 — Tax environment selection**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Admin shall select `Tax-based` or `Non-tax` during company creation.

---

## 7. Tenant Provisioning and Schema Families

**FR-TEN-001 — Separate templates**  
Origin: `QUANTITY-NEW`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Serial and quantity companies shall have independently maintained tenant schema
templates. The existing serial template shall not be repurposed into a
conditional mixed schema.

**FR-TEN-002 — Separate hardening**  
Origin: `QUANTITY-NEW`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Each schema family shall have an idempotent production-hardening path.
Serial hardening shall run only against serial schemas and quantity hardening
only against quantity schemas.

**FR-TEN-003 — Schema family metadata**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Every tenant schema shall store:

- Schema family (`serial` or `quantity`).
- Schema version.
- Provisioning timestamp where practical.

Middleware or schema activation logic shall verify that public company type and
tenant schema family agree.

**FR-TEN-004 — Atomic provisioning**  
Origin: `SERIAL-PARITY`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Provisioning shall be transactional or compensating. A failed schema build
shall not leave an active company that appears usable.

**FR-TEN-005 — Provisioning idempotency**  
Origin: `SERIAL-PARITY`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Retries shall not duplicate tables, seed data, accounts, parties, sequences, or
schema-version rows.

**FR-TEN-006 — Schema-version enforcement**  
Origin: `SHARED-PLATFORM`, `SERIAL-PARITY`  
Priority: `P0`

The required schema version shall be selected by family. An outdated or
mismatched schema shall be denied safely without causing a login redirect loop.

**FR-TEN-007 — Existing-tenant upgrades**  
Origin: `SERIAL-PARITY`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Every quantity database change shall include:

- Fresh-template behavior.
- An idempotent patch for existing quantity tenants.
- Quantity production hardening where the change is essential.
- An all-quantity-tenant rollout command.
- Version and post-upgrade verification.

**FR-TEN-008 — Search-path safety**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

All requests, admin utilities, management commands, tests, and failures shall
reset `search_path` to `public` after tenant work.

---

## 8. Product and Variant Requirements

### 8.1 Item Master

**FR-ITEM-001 — Shared item concepts**  
Origin: `SERIAL-ADAPTED`  
Priority: `P1`

Quantity items shall retain applicable serial-system concepts including item
name, brand, category, active status, and lookup/autocomplete behavior.

**FR-ITEM-002 — Variant dimensions**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

The quantity schema shall support these variant dimensions:

- Brand.
- Model.
- Color.
- Storage.
- RAM.
- Region.
- Condition.

**FR-ITEM-003 — Unique SKU**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Every unique sellable variant combination shall have one unique SKU within the
tenant.

**FR-ITEM-004 — SKU suggestion and editing**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P1`

The system shall suggest a SKU from variant attributes. An authorized user may
replace the suggestion. SKU editing shall be blocked after any business
transaction references the variant.

**FR-ITEM-005 — Variant uniqueness**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Database constraints shall prevent duplicate active variant combinations and
duplicate SKUs according to normalized comparison rules.

**FR-ITEM-006 — Variant identity in reports**  
Origin: `QUANTITY-NEW`  
Priority: `P1`

Every stock and profitability report shall allow a user to distinguish the
full variant combination, not only the parent item/model.

### 8.2 Units of Measure

**FR-UOM-001 — Supported units**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

The first release shall support at least:

- Piece.
- Box.
- Kilogram.
- Gram.
- Litre.
- Metre.

**FR-UOM-002 — Precision**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Quantity storage shall support up to three decimal places. Piece and Box items
shall accept whole numbers only. Weight, volume, and length items may use up to
three decimal places.

**FR-UOM-003 — One unit per SKU**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Each SKU shall have exactly one inventory unit. The system shall not convert
between Box and Piece or any other units.

**FR-UOM-004 — Unit immutability**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

An SKU’s unit shall not be changed after inventory transactions exist.

---

## 9. Warehouse Requirements

**FR-WH-001 — Multiple warehouses**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Quantity companies shall support multiple warehouses in the first release.

**FR-WH-002 — Warehouse master**  
Origin: `QUANTITY-NEW`  
Priority: `P1`

Authorized users shall create, rename, activate, and deactivate warehouses.
A warehouse referenced by transactions shall not be hard-deleted.

**FR-WH-003 — Default warehouse**  
Origin: `QUANTITY-NEW`  
Priority: `P1`

A company may configure a default warehouse for faster transaction entry.
Every inventory movement shall nevertheless store an explicit warehouse.

**FR-WH-004 — Warehouse-aware availability**  
Origin: `QUANTITY-NEW`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Availability shall be calculated per SKU and warehouse. Quantity in another
warehouse shall not permit a sale unless an approved transfer is posted.

**FR-WH-005 — Transfers**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Authorized users shall transfer stock from one warehouse to another.
A transfer shall:

- Use a unique sequential transfer number.
- Record date, source, destination, items, quantities, user, and description.
- Reduce source availability and increase destination availability atomically.
- Preserve FIFO cost identity and total company inventory value.
- Reject identical source/destination warehouses.
- Reject quantities exceeding source availability.
- Support guarded correction or reversal.
- Appear in movement and audit reports.

**FR-WH-006 — Transfer accounting**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

A normal transfer between warehouses within the same company shall not create
revenue, expense, profit, receivable, or payable. If warehouse-level inventory
control accounts are later introduced, entries must net to zero at company
level.

---

## 10. Inventory and FIFO Requirements

**FR-INV-001 — FIFO costing**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Quantity inventory shall use perpetual FIFO cost layers.

**FR-INV-002 — FIFO layer creation**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Opening stock, purchases, and eligible sale returns shall create or restore
costed inventory quantities according to the approved return rules.

**FR-INV-003 — FIFO consumption**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Sales, purchase returns, and negative adjustments shall consume eligible
quantity and costs transactionally according to FIFO and source restrictions.

**FR-INV-004 — Cost-consumption trace**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Every sale line shall retain a durable allocation from sold quantity to the
FIFO layers consumed. This trace is required for exact COGS, returns, edits,
deletions, and audit.

**FR-INV-005 — No negative stock**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

No operation may make available stock negative, including:

- Sale.
- Purchase return.
- Transfer.
- Adjustment.
- Edit.
- Delete/reversal.
- Backdated insertion.
- Concurrent transaction.

**FR-INV-006 — Insufficient-stock warning**  
Origin: `OWNER-APPROVED`  
Priority: `P1`

The UI/API shall clearly state requested quantity, available quantity, SKU, and
warehouse when an operation is blocked. No warning may act as an override.

**FR-INV-007 — Movement ledger**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Every stock change shall create an immutable movement record containing:

- SKU/item/variant.
- Warehouse.
- Movement timestamp and business date.
- Direction and quantity.
- Source document type, ID, line, and display number.
- Unit/cost value as required.
- User.
- Description/reason.
- Reversal/original linkage where applicable.

**FR-INV-008 — Reconciliation equation**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

For each SKU and warehouse:

`closing = opening + purchases + sale returns + inbound transfers + positive adjustments - sales - purchase returns - outbound transfers - negative adjustments`

System stock, movement totals, and FIFO remaining quantities shall agree.

---

## 11. Purchase Requirements

**FR-PUR-001 — Quantity purchase entry**  
Origin: `SERIAL-ADAPTED`, `QUANTITY-NEW`  
Priority: `P0`

A purchase shall accept vendor, warehouse, invoice date, document number,
currency/rate when foreign, description, attachments, and one or more lines
containing SKU, quantity, unit price/cost, discount, and tax.

**FR-PUR-002 — No serial entry**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Quantity purchase screens and APIs shall not request or generate serial
numbers.

**FR-PUR-003 — Posting**  
Origin: `SERIAL-PARITY`, `SERIAL-ADAPTED`  
Priority: `P0`

Posting a credit purchase shall increase warehouse stock/FIFO layers, debit
Inventory, and credit vendor Accounts Payable for the correct base-currency
amount, with tax treatment as configured.

**FR-PUR-004 — Cash purchase**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

Cash purchases shall credit Cash/Bank instead of leaving a vendor payable and
shall retain existing cash-party semantics.

**FR-PUR-005 — Purchase edit**  
Origin: `SERIAL-ADAPTED`, `OWNER-APPROVED`  
Priority: `P0`

Posted purchases may be edited only through a database operation that
atomically recalculates affected FIFO layers, later COGS, inventory, journals,
party balances, taxes, discounts, and reports.

**FR-PUR-006 — Unsafe edit block**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

An edit shall be rejected if later dependency preservation cannot be proven or
if any point in the rebuilt timeline would create negative stock.

**FR-PUR-007 — Purchase deletion/reversal**  
Origin: `SERIAL-PARITY`, `SERIAL-ADAPTED`  
Priority: `P0`

Deletion/reversal shall be blocked when purchased quantity has dependent sale,
return, transfer, or adjustment consumption that cannot be safely rebuilt.
Historical document numbers shall never be reused.

**FR-PUR-008 — Navigation and summary**  
Origin: `SERIAL-PARITY`  
Priority: `P1`

Current, previous, next, last, date range, and purchase summary behavior shall
be available for quantity purchases.

---

## 12. Sale Requirements

**FR-SAL-001 — Quantity sale entry**  
Origin: `SERIAL-ADAPTED`, `QUANTITY-NEW`  
Priority: `P0`

A sale shall accept customer, warehouse, invoice date, currency/rate when
foreign, description, attachments, and one or more lines containing SKU,
quantity, unit price, discount, and tax.

**FR-SAL-002 — Manual quantity**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Users shall enter quantity directly. Serial lookup, serial lists, and
serial-count validation shall not appear for quantity companies.

**FR-SAL-003 — Availability check**  
Origin: `SERIAL-ADAPTED`  
Priority: `P0`

The database shall lock and verify warehouse availability during posting. A
prior browser availability result shall not be trusted as authoritative.

**FR-SAL-004 — FIFO COGS**  
Origin: `SERIAL-ADAPTED`, `OWNER-APPROVED`  
Priority: `P0`

Posting shall consume FIFO layers, persist allocations, recognize revenue, and
post exact COGS and Inventory reduction.

**FR-SAL-005 — Credit sale accounting**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

Credit sales shall debit customer Accounts Receivable and credit Revenue/tax
liabilities as applicable.

**FR-SAL-006 — Cash sale accounting**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

Cash sales shall debit Cash/Bank and shall not leave customer receivables.

**FR-SAL-007 — Sale edit**  
Origin: `SERIAL-ADAPTED`, `OWNER-APPROVED`  
Priority: `P0`

Posted sales may be edited when the complete stock/FIFO/journal/return timeline
can be rebuilt atomically without violating stock, return, close, or accounting
guards.

**FR-SAL-008 — Sale mutation after return**  
Origin: `SERIAL-PARITY`, `ENGINEERING-MANDATORY`  
Priority: `P0`

An edit or deletion that would invalidate an existing sale return shall be
blocked or handled by an explicitly safe rebuild. It shall never orphan return
quantities or cost allocations.

**FR-SAL-009 — Duplicate submission**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Double-clicks, retries, or repeated requests shall not create duplicate sales
or duplicate inventory/journal movements.

---

## 13. Sale Return Requirements

**FR-SR-001 — Source linkage**  
Origin: `SERIAL-ADAPTED`  
Priority: `P0`

Every sale-return line shall reference an eligible original sale line and SKU.

**FR-SR-002 — Partial returns**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Multiple partial returns are allowed. Cumulative returned quantity shall never
exceed the original sale-line quantity.

**FR-SR-003 — Customer validation**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

The return customer shall match the source sale customer, subject only to an
explicitly documented cash-sale rule.

**FR-SR-004 — Original cost restoration**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Sale return shall reverse the exact historical FIFO COGS allocated to the
returned quantity and restore that cost to inventory.

**FR-SR-005 — Warehouse restoration**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Returned stock shall enter an explicitly selected warehouse. The default should
be the source sale warehouse; a different warehouse requires permission and
must be recorded.

**FR-SR-006 — Accounting reversal**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

The return shall reverse revenue/receivable or cash and applicable tax, reverse
COGS, and restore Inventory.

**FR-SR-007 — Return update/delete**  
Origin: `SERIAL-ADAPTED`  
Priority: `P0`

Updates or deletion/reversal shall rebuild affected quantities, FIFO layers,
journals, taxes, customer balances, and later dependencies atomically.

---

## 14. Purchase Return Requirements

**FR-PR-001 — Source linkage**  
Origin: `SERIAL-ADAPTED`  
Priority: `P0`

Every purchase-return line shall reference an eligible original purchase line,
SKU, and quantity.

**FR-PR-002 — Partial returns**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Multiple partial purchase returns are allowed. Cumulative returned quantity
shall never exceed the original purchase-line quantity.

**FR-PR-003 — Vendor validation**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

The vendor shall match the source purchase vendor, subject only to documented
cash-purchase behavior.

**FR-PR-004 — Original cost**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Purchase return shall use the original purchase-line unit cost.

**FR-PR-005 — Eligibility guard**  
Origin: `SERIAL-ADAPTED`, `OWNER-APPROVED`  
Priority: `P0`

The return shall be blocked unless sufficient eligible quantity from the
purchase can be established under FIFO/source-allocation rules. Quantity
already consumed in downstream transactions cannot be returned unless a safe
rebuild restores eligibility.

**FR-PR-006 — Accounting reversal**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

The return shall reduce Inventory and vendor payable or restore Cash/Bank as
applicable, including correct tax reversal.

---

## 15. Opening Stock, Counts, and Adjustments

**FR-OPEN-001 — Opening stock**  
Origin: `SERIAL-ADAPTED`  
Priority: `P0`

Opening stock shall accept warehouse, SKU, quantity, unit cost, date, and
description without serials and shall create FIFO opening layers.

**FR-OPEN-002 — Opening accounting**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

Opening stock shall debit Inventory and credit the existing Opening Balance
account, with the existing reclassification-to-capital workflow preserved.

**FR-COUNT-001 — Physical count session**  
Origin: `QUANTITY-NEW`, `OWNER-APPROVED`  
Priority: `P0`

Authorized users shall create a physical count for a warehouse and record
counted quantities by SKU.

**FR-COUNT-002 — Variance**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

The system shall show system quantity, counted quantity, and variance as of the
count cutoff.

**FR-COUNT-003 — Approval and posting**  
Origin: `QUANTITY-NEW`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Counts shall not change stock until approved by a user with adjustment
permission. Posting shall be atomic and audited.

**FR-ADJ-001 — Adjustment requirements**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Every adjustment shall require warehouse, SKU, quantity difference, reason,
user, date, and approval.

**FR-ADJ-002 — Negative adjustment guard**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

A negative adjustment shall not exceed available quantity.

**FR-ADJ-003 — Adjustment valuation**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Negative adjustments shall consume FIFO cost. Positive adjustments shall use an
approved entered cost or documented valuation rule.

**FR-ADJ-004 — Adjustment accounting**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Adjustments shall post balanced Inventory and adjustment gain/loss entries and
appear in profit/expense and audit reports.

---

## 16. Shared Financial Modules

The following modules shall retain serial-system accounting semantics and gain
only the minimum changes required to work with quantity-company schemas:

**FR-FIN-001 — Parties** (`SERIAL-PARITY`, `P0`)  
Customer, vendor, both, expense, cash sentinel, opening balances, lookup,
update, and balance behavior shall remain available.

**FR-FIN-002 — Payments** (`SERIAL-PARITY`, `P0`)  
Create, fetch, update, delete/reverse, history, party balance, description, and
attachment behavior shall remain available.

**FR-FIN-003 — Receipts** (`SERIAL-PARITY`, `P0`)  
Create, fetch, update, delete/reverse, history, party balance, description, and
attachment behavior shall remain available.

**FR-FIN-004 — Contra** (`SERIAL-PARITY`, `P0`)  
Contra posting, same-party guard, update/delete behavior, description, and
attachments shall remain available.

**FR-FIN-005 — Owner equity** (`SERIAL-PARITY`, `P0`)  
Capital injection/withdrawal, listing, validation, and reversal shall remain.

**FR-FIN-006 — Opening cash** (`SERIAL-PARITY`, `P0`)  
Singleton opening-cash behavior and accounting shall remain.

**FR-FIN-007 — Month close** (`SERIAL-PARITY`, `P0`)  
Preview, close, duplicate guard, listing, reversal, and closed-period write
enforcement shall cover all new quantity operations.

**FR-FIN-008 — Balanced journals** (`SERIAL-PARITY`, `P0`)  
No successful business operation may leave an unbalanced or empty journal.

---

## 17. Tax Requirements

**FR-TAX-001 — Company tax mode**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Company creation shall select tax-based or non-tax.

**FR-TAX-002 — Non-tax companies**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Non-tax companies shall not require tax selection and shall not post tax
control-account lines.

**FR-TAX-003 — Tax configuration**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Authorized admins shall configure tenant tax name, code, percentage, active
status, and related control account.

**FR-TAX-004 — Tax classifications**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Tax-based companies shall support:

- Taxable lines.
- Zero-rated lines.
- Exempt lines.
- Optional exemption reason/reference.

**FR-TAX-005 — Inclusive/exclusive**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Tax-based companies shall support both inclusive and exclusive prices, with a
company default and explicit invoice-level selection stored historically.

**FR-TAX-006 — Per-line calculation**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Tax shall be calculated per line after applicable discounts. Invoice UI,
stored document, print/export, journal, and reports shall summarize taxes by
code/rate.

**FR-TAX-007 — Historical stability**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Invoices shall store the tax code, rate, mode, taxable value, and tax amount
actually applied. Editing a tax configuration shall not alter historical
documents.

**FR-TAX-008 — Return tax reversal**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Partial returns shall reverse tax proportionally from the exact original line
calculation without exceeding remaining returnable tax.

---

## 18. Discount Requirements

**FR-DISC-001 — Discount types**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Support percentage and fixed-amount discounts.

**FR-DISC-002 — Discount levels**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Support discounts at line level and whole-invoice level.

**FR-DISC-003 — Calculation order**  
Origin: `OWNER-APPROVED`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Default calculation order:

1. Quantity multiplied by unit price.
2. Line discount.
3. Proportional allocation of invoice discount across eligible lines.
4. Tax calculated on each discounted line.
5. Invoice totals and rounding adjustment.

**FR-DISC-004 — Validation**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Discounts shall not create negative line values, negative taxable values, or
invalid tax. Percentage discounts shall be bounded from 0% through 100%.

**FR-DISC-005 — Historical values**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Store discount type, input value, allocated amount, and calculation results on
the document. Later configuration changes shall not recalculate history.

---

## 19. Currency Requirements

**FR-CUR-001 — Currency catalogue**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

The public/shared system shall provide a worldwide currency catalogue with ISO
code, name, symbol, and monetary precision.

**FR-CUR-002 — Base currency**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Every company shall have one base accounting/reporting currency.

**FR-CUR-003 — Domestic documents**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Documents in base currency shall not request an exchange rate.

**FR-CUR-004 — International documents**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

An invoice whose transaction currency differs from base currency shall store:

- Transaction currency.
- Foreign subtotal, discounts, tax, and total.
- Manually entered invoice exchange rate.
- Base-currency equivalents.

**FR-CUR-005 — Manual rate**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Exchange rates shall be manually entered on each international purchase or sale
invoice. The system shall not depend on an internet rate provider.

**FR-CUR-006 — Settlement rate**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Payment/receipt against a foreign invoice shall accept the settlement-date
exchange rate and foreign amount settled.

**FR-CUR-007 — Realized gain/loss**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

The system shall automatically post realized exchange gain or loss equal to
the difference between:

- Base value of the settled foreign amount at original invoice allocation
  rates; and
- Base cash/bank value at settlement rate.

**FR-CUR-008 — Partial settlement**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Partial payments and receipts shall calculate realized gain/loss only on the
foreign amount being settled and shall maintain the remaining foreign balance.

**FR-CUR-009 — Reporting**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Realized exchange gain/loss shall appear in profit, expense, ledger, and
transaction reports.

**FR-CUR-010 — No unrealized revaluation**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Unpaid foreign invoices shall remain at their original posted base value until
settlement. Month close shall not post unrealized currency revaluation.

---

## 20. Numbering Requirements

**FR-NUM-001 — Independent sequences**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Each tenant and document type shall use a transactionally generated sequence.
Examples include:

- `PUR-000001`
- `SAL-000001`
- `PR-000001`
- `SR-000001`
- `PAY-000001`
- `REC-000001`
- `CON-000001`
- `TRF-000001`
- `ADJ-000001`
- `CNT-000001`

**FR-NUM-002 — Concurrency**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Simultaneous document creation shall not generate duplicate numbers.

**FR-NUM-003 — No reuse**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Voided, reversed, failed-after-number-reservation, or deleted document numbers
shall not be reassigned.

**FR-NUM-004 — Internal identity**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P1`

Database primary keys shall remain separate from user-facing document numbers.

---

## 21. Backdating and Editing

**FR-DATE-001 — Open periods only**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

Backdated inventory and financial documents shall be accepted only in open
accounting periods.

**FR-DATE-002 — Timeline rebuild**  
Origin: `OWNER-APPROVED`, `ENGINEERING-MANDATORY`  
Priority: `P0`

A backdated create/edit/delete shall rebuild affected FIFO layers, allocations,
COGS, movement balances, journals, party balances, and reports in chronological
order under appropriate locks.

**FR-DATE-003 — Historical negative-stock guard**  
Origin: `OWNER-APPROVED`  
Priority: `P0`

The operation shall be rejected if stock becomes negative at any affected
historical point, even if current closing stock remains positive.

**FR-DATE-004 — Atomicity**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

The entire rebuild shall commit or roll back as one database transaction.

**FR-DATE-005 — Explain blocked mutation**  
Origin: `QUANTITY-NEW`  
Priority: `P1`

When an edit is unsafe, the user shall receive a clear reason and the dependent
document(s) preventing it without leaking another tenant’s information.

---

## 22. Attachments and Descriptions

**FR-ATT-001 — Supported documents**  
Origin: `SHARED-PLATFORM`, `SERIAL-PARITY`  
Priority: `P0`

Image/PDF attachments and descriptions shall work for quantity purchases,
sales, returns, payments, receipts, and contra, and for new transfer,
adjustment, and count documents where approved.

**FR-ATT-002 — Tenant-private access**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

Only authenticated users with document permission in the owning tenant may
view or download an attachment.

**FR-ATT-003 — Cleanup semantics**  
Origin: `SERIAL-PARITY`  
Priority: `P0`

Files shall be removed only after successful business deletion/reversal rules
permit cleanup. A failed transaction mutation shall not remove attachments.

**FR-ATT-004 — Validation**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

Existing type, size, filename, storage-path, and feature-flag validation shall
apply.

---

## 23. UI and User Experience

**FR-UI-001 — Same theme**  
Origin: `SERIAL-PARITY`, `OWNER-APPROVED`  
Priority: `P1`

Serial and quantity companies shall use the same visual theme, responsive
layout, navigation conventions, and custom admin styling.

**FR-UI-002 — Mode-aware forms**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Serial users shall continue to see serial controls. Quantity users shall see
quantity, unit, warehouse, variant, tax, discount, and currency controls.

**FR-UI-003 — No client-authoritative accounting**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Client calculations are previews. PostgreSQL results shall be authoritative.

**FR-UI-004 — Alerts**  
Origin: `SHARED-PLATFORM`  
Priority: `P1`

All user-facing alerts shall use the existing `Alerts` helper and established
success/error/warning/confirmation conventions.

**FR-UI-005 — Duplicate-submit protection**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

The UI shall disable repeated submission while posting, and the backend shall
remain idempotent/guarded if duplicate requests still arrive.

**FR-UI-006 — Spreadsheet entry**  
Origin: `SERIAL-PARITY`  
Priority: `P1`

Existing smart-description/spreadsheet-paste behavior shall remain where
applicable. Any bulk line paste shall validate warehouse, SKU, quantity, unit,
tax, and discounts before posting.

---

## 24. Reports

Every report shall:

- Enforce permissions and feature flags.
- Use the authenticated tenant schema.
- Accept valid date/filter inputs.
- Return no data from another tenant.
- Reconcile to source transactions and accounting.
- Provide CSV/Excel export when the company’s export feature is enabled.
- Store/display base currency and foreign values where relevant.
- Meet the performance targets in this SRS.

### 24.1 Accounts Reports

**REP-ACC-001 — Trial Balance** (`SERIAL-PARITY`, `P0`)  
Debit and credit totals shall balance.

**REP-ACC-002 — Detailed Party Ledger** (`SERIAL-ADAPTED`, `P0`)  
Invoice details shall show quantities/SKUs rather than serial lists.

**REP-ACC-003 — Cash Ledger** (`SERIAL-PARITY`, `P0`)  
Cash/bank movements and counterparties shall remain visible.

**REP-ACC-004 — Accounts Receivable** (`SERIAL-PARITY`, `P0`)

**REP-ACC-005 — Accounts Payable** (`SERIAL-PARITY`, `P0`)

**REP-ACC-006 — Monthly Company Position** (`SERIAL-ADAPTED`, `P0`)  
Inventory assets shall use quantity FIFO valuation.

**REP-ACC-007 — Monthly Income Statement/Month-End Profit** (`SERIAL-ADAPTED`, `P0`)  
Include sales, returns, COGS, expenses, discounts, tax treatment where
appropriate, inventory adjustments, and realized exchange gain/loss.

**REP-ACC-008 — Expense Report** (`QUANTITY-NEW`, `OWNER-APPROVED`, `P0`)  
Provide date, account/category, party, description, document, warehouse where
relevant, amount, and comparison totals.

### 24.2 Stock Reports

**REP-STK-001 — Stock Summary** (`SERIAL-ADAPTED`, `P0`)  
Show opening, inward, outward, and closing quantity by SKU and warehouse.

**REP-STK-002 — Stock Valuation** (`SERIAL-ADAPTED`, `P0`)  
Show remaining FIFO layers and total inventory value.

**REP-STK-003 — Item Movement Ledger** (`QUANTITY-NEW`, `P0`)  
Show chronological quantity in/out, running balance, cost, warehouse, and
source.

**REP-STK-004 — Item Transaction History** (`SERIAL-ADAPTED`, `P0`)

**REP-STK-005 — Last Purchase and Last Sale** (`SERIAL-ADAPTED`, `P1`)

**REP-STK-006 — Low Stock/Reorder Report** (`QUANTITY-NEW`, `P1`)

**REP-STK-007 — Stock Aging** (`QUANTITY-NEW`, `P1`)  
Age remaining FIFO quantities/value.

**REP-STK-008 — Fast/Slow Moving Items** (`QUANTITY-NEW`, `P1`)

**REP-STK-009 — Integrity Exception Report** (`QUANTITY-NEW`, `P0`)  
Expose movement/FIFO/stock/value inconsistencies and negative states; expected
normal result is empty.

**REP-STK-010 — Inventory Movement Reconciliation** (`QUANTITY-NEW`, `P0`)

**REP-STK-011 — Inventory Valuation Reconciliation** (`QUANTITY-NEW`, `P0`)  
Reconcile FIFO stock valuation to the Inventory control-account balance.

**REP-STK-012 — Warehouse Transfer Report** (`QUANTITY-NEW`, `P1`)

**REP-STK-013 — Physical Count and Adjustment Report** (`QUANTITY-NEW`, `P0`)

### 24.3 Sales Reports

**REP-SAL-001 — Daily Sales Report** (`SERIAL-ADAPTED`, `OWNER-APPROVED`, `P0`)

**REP-SAL-002 — Sales Summary** (`SERIAL-ADAPTED`, `P0`)  
Quantity, gross sales, discounts, taxes, returns, net sales, COGS, and gross
profit.

**REP-SAL-003 — Product Profitability** (`SERIAL-ADAPTED`, `P0`)

**REP-SAL-004 — Customer Profitability** (`SERIAL-ADAPTED`, `P0`)

**REP-SAL-005 — Sales by Product/SKU/Variant** (`SERIAL-ADAPTED`, `P0`)

**REP-SAL-006 — Sales by Customer** (`SERIAL-PARITY`, `P0`)

**REP-SAL-007 — Sale-Wise Profit** (`SERIAL-ADAPTED`, `P0`)

**REP-SAL-008 — Sales Trend** (`SERIAL-PARITY`, `P1`)

**REP-SAL-009 — Invoice Register** (`SERIAL-ADAPTED`, `P0`)

**REP-SAL-010 — Gross Margin Analysis** (`QUANTITY-NEW`, `P0`)  
Filter by SKU, model, category, customer, warehouse, and period.

**REP-SAL-011 — Return Rate Analysis** (`QUANTITY-NEW`, `P1`)

### 24.4 Purchase Reports

**REP-PUR-001 — Purchase Register** (`QUANTITY-NEW`, `OWNER-APPROVED`, `P0`)

**REP-PUR-002 — Purchases by Vendor** (`QUANTITY-NEW`, `P1`)

**REP-PUR-003 — Purchases by Product/SKU** (`QUANTITY-NEW`, `P1`)

**REP-PUR-004 — Purchase Return Analysis** (`QUANTITY-NEW`, `P1`)

**REP-PUR-005 — Purchase Price Variance** (`QUANTITY-NEW`, `P1`)

### 24.5 Reports Unavailable to Quantity Companies

The following existing reports remain available to serial companies but shall
be hidden and backend-blocked for quantity companies:

| Existing report | Reason unavailable in quantity mode | Replacement |
|---|---|---|
| Serial Ledger | No individual serial identity exists. | Item Movement Ledger |
| Serial Ledger with Sold Flag | Stock status is aggregate quantity by warehouse. | Stock Summary / Movement Ledger |
| Serial Purchase-Only Ledger | Purchases are traced by SKU, line, quantity, and FIFO layer. | Purchase Register / Item Movement |
| Serial Sale-Only Ledger | Sales are traced by SKU, line, and FIFO allocations. | Sales by SKU / Item Movement |
| Serial Number Details/Lookup | Quantity tenants never create serial numbers. | SKU/Variant details and movement history |

No serial report, route, permission, or SQL object shall be removed from the
serial schema merely because it is unsupported for quantity tenants.

---

## 25. Dashboard Requirements

**FR-DASH-001 — Shared dashboard purpose**  
Origin: `SERIAL-ADAPTED`  
Priority: `P1`

Quantity dashboards shall provide sales KPIs, sales chart, stock KPIs,
low-stock, fast-moving, stale stock, top customers/vendors, receivables aging,
recent transactions, expenses, and smart alerts.

**FR-DASH-002 — Quantity semantics**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Stock dashboard functions shall calculate SKU/warehouse quantities and FIFO
values rather than serial counts.

**FR-DASH-003 — Fan-out and rate limits**  
Origin: `SHARED-PLATFORM`  
Priority: `P1`

Existing Redis-backed rate limiting shall apply. Dashboard concurrency shall
not leak tenant context or exhaust PostgreSQL connections.

---

## 26. Permissions, Features, and Subscription

**FR-SEC-001 — Route permissions**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

Every new route shall be included in the central permission mapping and shall
also check permissions at the view level where current conventions require it.

**FR-SEC-002 — Quantity permissions**  
Origin: `QUANTITY-NEW`  
Priority: `P0`

Add explicit Django permissions for warehouses, transfers, counts,
adjustments, quantity reports, and relevant exports.

**FR-FEAT-001 — Feature catalogue by type**  
Origin: `SHARED-PLATFORM`, `QUANTITY-NEW`  
Priority: `P0`

Feature availability shall be selected centrally by company type. Unsupported
serial-only reports cannot be enabled for quantity tenants.

**FR-FEAT-002 — UI and backend agreement**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

Disabled features shall be hidden in templates/JavaScript and blocked at the
backend. Direct URL/API calls shall not bypass flags.

**FR-SUB-001 — Subscription behavior**  
Origin: `SHARED-PLATFORM`  
Priority: `P0`

Paid-until, grace, automatic blocking, manual suspension, payment recording,
warnings, and subscription emails shall work identically for both company
types.

---

## 27. Audit Requirements

**FR-AUD-001 — Mutation audit**  
Origin: `ENGINEERING-MANDATORY`  
Priority: `P0`

Record tenant, user, time, action, document type/ID/number, old/new values or
change summary, IP/request identifier where available, and result for:

- Company creation and selected type.
- Product/SKU and warehouse changes.
- Every financial/inventory create, edit, reversal, delete, return, transfer,
  count, adjustment, and close.
- Tax/currency configuration.
- Permission and feature changes.
- Attachment upload/replacement/deletion.
- Report export.
- Authorization failure.

**FR-AUD-002 — Historical attribution**  
Origin: `SERIAL-PARITY`, `ENGINEERING-MANDATORY`  
Priority: `P0`

Deactivating a user shall not remove their historical transaction attribution.

---

## 28. Non-Functional Requirements

### 28.1 Security and Isolation

**NFR-SEC-001** (`P0`) No tenant shall read, alter, infer, cache, export, or
download another tenant’s data.

**NFR-SEC-002** (`P0`) Schema identifiers shall pass existing validation and
quoting helpers; raw identifiers shall never be interpolated from user input.

**NFR-SEC-003** (`P0`) JSON errors shall not expose SQL, schema, filesystem,
secret, or stack-trace details.

**NFR-SEC-004** (`P0`) Attachment paths shall remain private and tenant checked.

**NFR-SEC-005** (`P0`) Permissions and feature flags shall be enforced
server-side.

### 28.2 Data Integrity

**NFR-DATA-001** (`P0`) Business posting and its inventory/accounting effects
shall be atomic.

**NFR-DATA-002** (`P0`) Database constraints and stored functions shall enforce
critical invariants independently of browser validation.

**NFR-DATA-003** (`P0`) All money calculations shall use fixed-precision
numeric types, never floating point.

**NFR-DATA-004** (`P0`) Quantity shall use fixed precision up to three decimals.

**NFR-DATA-005** (`P0`) Historical tax, discount, currency, and FIFO allocations
shall remain reproducible.

### 28.3 Performance and Capacity

**NFR-PERF-001** (`P0`) Validate at least 100 concurrent active sessions.

**NFR-PERF-002** (`P0`) Validate at least 100,000 SKUs per tenant.

**NFR-PERF-003** (`P0`) Validate at least five million stock movements.

**NFR-PERF-004** (`P0`) Normal reports shall complete within three seconds under
the defined representative load. Heavy exports may run separately with visible
progress.

**NFR-PERF-005** (`P1`) Validate a pilot profile of approximately 100,000
physical units across warehouses, 100 invoices/day, and 30–40 other daily
transactions.

**NFR-PERF-006** (`P0`) Load testing shall determine whether the current
2-vCPU/4-GiB `t4g.medium` is sufficient. Production configuration shall not
assume an 8-GiB host.

### 28.4 Availability and Recoverability

**NFR-OPS-001** (`P0`) A verified off-server database and media backup shall
exist before live migration.

**NFR-OPS-002** (`P0`) Restore shall be rehearsed before production approval.

**NFR-OPS-003** (`P0`) Deployment health checks shall cover login and at least
one safe endpoint for each schema family.

**NFR-OPS-004** (`P0`) Database migrations and tenant SQL shall be
backward-compatible with application rollback.

### 28.5 Maintainability

**NFR-MAIN-001** (`P0`) Schema-family selection shall be centralized, not
repeated as arbitrary conditionals throughout views.

**NFR-MAIN-002** (`P0`) Shared HTTP/auth/permission/attachment behavior should
be reused; inventory SQL and payload rules shall remain explicitly separated.

**NFR-MAIN-003** (`P0`) `PROJECT_CONTEXT.md`, SQL catalogues, test results, and
deployment documentation shall be updated with every material design change.

---

## 29. Data Model Requirements

The final physical model will be produced in Phase 1/2, but it shall represent
at least these logical entities:

### 29.1 Public Schema

- Company, including immutable company type, base currency, and tax mode.
- Membership.
- Subscription payment.
- Billing/email settings.
- Subscription email log.
- Worldwide currency catalogue or equivalent controlled reference.

### 29.2 Quantity Tenant Schema

- Tenant schema metadata/version.
- Chart of accounts.
- Journal entries and journal lines.
- Parties.
- Items/products.
- Variant dimension values and sellable SKU.
- Units of measure.
- Warehouses.
- Tax codes/configuration.
- Document-number sequences.
- Purchase headers and lines.
- Sale headers and lines.
- Purchase-return headers and lines.
- Sale-return headers and lines.
- Payments and allocations.
- Receipts and allocations.
- Contra entries.
- FIFO layers.
- FIFO consumption allocations.
- Stock movements.
- Warehouse transfers and lines.
- Physical count sessions and lines.
- Inventory adjustments and lines.
- Opening stock.
- Owner equity.
- Period closes.
- Document attachments.
- Audit events or an approved audit representation.

Every foreign key, uniqueness constraint, check constraint, deletion rule, and
index shall be documented in the Phase 1 logical/physical data model.

---

## 30. API and Backend Requirements

**INT-API-001 — Type-aware dispatch** (`P0`)  
Views shall dispatch through a controlled schema-family capability/service
layer.

**INT-API-002 — Payload separation** (`P0`)  
Quantity endpoints/functions shall reject serial payloads. Serial endpoints
shall preserve existing serial requirements and reject attempts to bypass them
with quantity-only payloads.

**INT-API-003 — Response compatibility** (`P1`)  
Where the frontend can share response shapes safely, common fields should
remain consistent. Mode-specific fields shall be explicitly documented.

**INT-API-004 — Validation** (`P0`)  
Validate types, precision, required values, permissions, warehouse, SKU,
currency, rate, tax, discounts, document state, and period before posting.
PostgreSQL shall repeat critical validation.

**INT-API-005 — Transactions** (`P0`)  
A backend request shall not manually assemble partial accounting across
multiple uncoordinated commits. One stored operation/transaction shall own each
business mutation.

---

## 31. Testing Requirements

### 31.1 Serial Non-Regression

**TST-SER-001** (`P0`) Run every existing serial test unchanged against two
serial tenants.

**TST-SER-002** (`P0`) Existing serial purchase, sale, returns, reports,
attachments, descriptions, subscriptions, feature flags, and accounting totals
shall remain unchanged.

### 31.2 Quantity Functional Coverage

Tests shall cover:

- Company creation/type/base currency/tax mode.
- Provisioning and version enforcement.
- Parties and opening balances.
- Items, variants, SKU generation/uniqueness/edit lock.
- Units and decimal/whole-number rules.
- Warehouses and transfers.
- Opening stock.
- Purchases and purchase returns.
- Sales and sale returns.
- FIFO creation, consumption, restoration, and rebuild.
- Taxes and discounts.
- Domestic and foreign currencies.
- Partial payments/receipts and realized exchange gain/loss.
- Physical counts and adjustments.
- Payments, receipts, contra, owner equity, and month close.
- Attachments and descriptions.
- Every dashboard function and report.
- Permissions, feature flags, subscriptions, and admin workflows.

### 31.3 Required Real-Life Flow

**TST-FLOW-001** (`P0`)

At minimum:

1. Purchase 100 units into Warehouse A.
2. Purchase the same SKU at another cost.
3. Transfer part to Warehouse B.
4. Sell 30 under FIFO.
5. Partially return 5 and restore original cost.
6. Resell 3.
7. Partially purchase-return eligible units.
8. Count stock and post a controlled variance.
9. Settle a foreign invoice partially at a changed rate.
10. Close the month and verify later blocked mutations.

Assert accounting and stock invariants after every step.

### 31.4 Invalid and Hostile Tests

Test zero/negative/excessive/fractionally invalid quantities, duplicate SKUs,
duplicate submission, excessive returns, wrong customer/vendor, unavailable
warehouse stock, same-warehouse transfer, unauthorized routes, disabled
features, malformed JSON, foreign rate omissions, excessive discounts, invalid
tax, closed periods, attachment abuse, and cross-mode payloads.

### 31.5 Concurrency

**TST-CON-001** (`P0`) Simultaneous sales shall not oversell.

**TST-CON-002** (`P0`) Simultaneous partial returns shall not exceed source
quantity.

**TST-CON-003** (`P0`) Simultaneous transfers/adjustments/edits shall preserve
FIFO and stock.

**TST-CON-004** (`P0`) Concurrent document numbering shall remain unique.

### 31.6 Four-Company Isolation Matrix

Provision:

- Serial Company A.
- Serial Company B.
- Quantity Company A.
- Quantity Company B.

Run concurrent writes, reads, reports, exports, failures, and attachment
downloads. Verify no data, file, cache key, report total, error detail, schema
state, or database connection context leaks across any pair.

### 31.7 Invariants

At every appropriate checkpoint:

- Debit equals credit.
- No empty journals.
- Party balances are exact.
- Cash/bank is exact.
- Revenue, discount, tax, and realized currency gain/loss are exact.
- FIFO COGS is exact.
- Stock movement balance equals closing stock.
- Remaining FIFO quantity equals stock.
- FIFO value reconciles to Inventory control account.
- Cumulative returns do not exceed sources.
- Closed periods reject prohibited changes.

---

## 32. CI/CD Requirements

**CICD-001** (`P0`) Django checks, byte compilation, and missing-migration guard
shall remain.

**CICD-002** (`P0`) CI shall provision the four-company matrix from a fresh
database.

**CICD-003** (`P0`) Serial and quantity suites shall appear as separate,
diagnosable stages.

**CICD-004** (`P0`) CI shall verify template, hardening, schema family, and
schema-version consistency.

**CICD-005** (`P0`) The published image shall support `linux/amd64` and
`linux/arm64`.

**CICD-006** (`P0`) The ARM64 artifact shall receive at least startup,
migration, provisioning, and HTTP smoke tests before production approval.

**CICD-007** (`P0`) Production deployment shall remain manual-approval gated
and use the SHA-pinned tested source.

**CICD-008** (`P0`) Deployment preflight shall list every tenant’s company type,
schema family, and schema version and stop on mismatch.

**CICD-009** (`P0`) A failed tenant upgrade shall identify the exact tenant and
shall not be reported as a successful rollout.

**CICD-010** (`P0`) Post-deployment checks shall verify at least one serial and
one quantity tenant when both exist.

---

## 33. Deployment and Rollout Requirements

1. Back up database and media off server.
2. Verify restore.
3. Deploy public migration that marks existing companies serial-based.
4. Verify existing public company/membership data.
5. Apply serial hardening only to serial tenants.
6. Run production-safe serial smoke checks.
7. Confirm current-company balances and reports.
8. Provision the first quantity company as a new pilot.
9. Verify quantity schema family/version.
10. Post controlled pilot transactions and reconcile.
11. Monitor errors, CPU credits, memory, disk, PostgreSQL connections, latency,
    and container health.
12. Keep rollback criteria and decision window active.

No existing company shall be converted during this rollout.

---

## 34. Acceptance Criteria

The feature is ready for live integration only when:

1. All P0 requirements are implemented and traceable to tests.
2. Two fresh serial and two fresh quantity companies provision successfully.
3. All existing serial tests pass unchanged on both serial companies.
4. All quantity functions, reports, routes, and workflows pass on both quantity
   companies.
5. Concurrent cross-tenant testing shows zero leakage.
6. FIFO, returns, backdating, edits, counts, transfers, tax, discounts, and
   foreign settlement reconcile exactly.
7. Trial balance remains balanced and Inventory reconciles to FIFO valuation.
8. Unsupported serial reports are absent and blocked for quantity tenants but
   remain available for serial tenants.
9. Backups, restore, migration, deployment, health check, and rollback are
   rehearsed in isolation/staging.
10. ARM64 smoke tests pass for the deployable image.
11. Capacity targets are tested and the production host is resized/tuned if
    required.
12. Security and tenant-isolation review finds no release-blocking defect.
13. Documentation, runbooks, report catalogue, schema catalogue, and latest
    test evidence are complete.
14. Product owner explicitly approves live integration.

---

## 35. Requirements Traceability Summary

| Area | Existing serial behavior retained | Quantity-specific change |
|---|---|---|
| Tenancy | Schema-per-company, membership, search path | Separate schema family/type/version |
| Accounting | Double entry, AR/AP, cash, revenue, COGS | FIFO quantity costing and reconciliation |
| Items | Item/category/brand concepts | Variants, SKU, unit precision |
| Purchases | Vendor, journal, navigation, attachments | Quantity lines, warehouse, FIFO layers |
| Sales | Customer/cash, revenue, journal, attachments | Quantity availability and FIFO allocation |
| Returns | Source validation and accounting reversal | Partial quantities and cost restoration |
| Stock | Inventory control and reports | Warehouses, movements, FIFO, counts, transfers |
| Reports | Accounts and sales concepts | Quantity/warehouse reports; serial reports removed only for quantity tenants |
| Admin | Custom admin, subscriptions, features | Type, base currency, tax mode |
| Security | Permissions, guards, rate limits | Mode/capability enforcement and hostile isolation tests |
| Deployment | Docker, CI/CD, ARM64, approval gate | Dual-family upgrade/preflight/smoke checks |

---

## 36. Approved Decisions Register

| Decision | Approved value |
|---|---|
| Costing | FIFO |
| Quantity precision | Up to 3 decimals |
| Whole-only units | Piece and Box |
| Other initial units | Kilogram, Gram, Litre, Metre |
| Negative stock | Prohibited; warning without override |
| Warehouses | Multiple |
| Batch/lot/expiry | Excluded |
| Variants | Brand, model, color, storage, RAM, region, condition |
| SKU | Unique per combination; suggested, editable before transactions |
| Unit conversion | Excluded; one unit per SKU |
| Backdating | Allowed in open periods with full safe rebuild |
| Posted editing | Allowed only with guarded atomic rebuild |
| Sale-return cost | Exact original FIFO COGS |
| Purchase-return cost | Original purchase cost with eligibility guard |
| Partial returns | Allowed; cumulative cap at source quantity |
| Physical counts | Included |
| Adjustments | Included with approval, reason, audit, and accounting |
| Company type | Immutable |
| Document numbering | Separate sequential number per type; no reuse |
| Tax company selection | Tax-based or non-tax at creation |
| Tax price modes | Inclusive and exclusive |
| Tax calculation | Per line, summarized per invoice |
| Tax classifications | Taxable, zero-rated, exempt |
| Discounts | Percentage/fixed; line/invoice; before tax |
| Base currency | Selected from worldwide catalogue at company creation |
| Foreign rate | Manually entered per international invoice |
| Settlement rate | Manually entered on foreign payment/receipt |
| Currency gain/loss | Realized only, including partial settlements |
| Unrealized revaluation | Excluded |
| Capacity target | 100 sessions, 100k SKUs, 5m movements, normal reports <3s |
| Pilot profile | Mobile/electronics wholesaler; ~100k physical units |
| Reports | Full approved quantity catalogue |
| Rollout | Existing three remain serial; new quantity pilot |

---

## 37. Change Control

Any change to an approved decision in Section 36 shall:

1. Be explicitly approved by the product owner.
2. Update this SRS and `PROJECT_CONTEXT.md`.
3. Identify affected SQL, backend, frontend, reports, tests, deployment, and
   existing/future tenants.
4. Add or update traceable acceptance tests.
5. Re-enter the appropriate architecture or release gate.

Implementation discoveries shall not silently redefine a requirement. If a
requirement is unsafe, ambiguous, or incompatible with another requirement,
development shall stop at the affected decision gate and present the conflict
with evidence and alternatives.
