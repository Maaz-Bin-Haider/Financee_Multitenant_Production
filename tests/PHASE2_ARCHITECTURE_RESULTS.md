# Phase 2 — Architecture and Schema-Family Design Results

**Date:** 2026-07-25  
**Result:** PASSED  
**Runtime implementation changes:** None  
**Primary artifact:** `ARCHITECTURE_QUANTITY_COMPANY.md`  
**Traceability artifact:** `REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md`

## Scope Completed

- Separate serial and quantity schema-family architecture.
- Central trusted schema-family registry/capability contract.
- Public Company metadata, currency catalogue, migration, backfill, and
  immutability design.
- Quantity tenant schema metadata/version/family verification.
- Logical product, variant, SKU, unit, warehouse, accounting, document, stock,
  FIFO, return, transfer, count, adjustment, tax, currency, numbering,
  attachment, and audit entities.
- FIFO allocation, exact sale-return restoration, purchase-return source
  eligibility, and transfer lineage.
- Backdated deterministic replay and dependency closure.
- Canonical concurrency lock order and idempotency.
- Document lifecycle, guarded editing, reversal, and close behavior.
- Fixed quantity, money, tax, and exchange-rate precision responsibilities.
- Backend capability and payload contracts.
- Report source/reconciliation matrix.
- Permissions, feature availability, provisioning, threat controls, and
  rollback compatibility.
- SRS-to-phase/component/SQL/test traceability.

## Design Walkthroughs

The following flows were traced through stock, FIFO, accounting, locking, and
reconciliation:

1. Multi-cost purchase → transfer → FIFO sale → exact-cost return.
2. Two concurrent sales competing for final stock.
3. Backdated purchase causing later FIFO/COGS replay.
4. Partial sale return → resale → excessive return rejection.
5. Foreign purchase → partial payment at changed rate → realized exchange loss.
6. Attempted mutation inside a closed period.

No approved product requirement contradicted another during the walkthroughs.

## Important Architecture Decisions

- Existing serial SQL remains independent and unchanged.
- Quantity V1 uses one warehouse per purchase/sale document.
- Multi-warehouse business is handled through separate documents and transfers.
- Quantity V1 posts directly; draft documents are deferred.
- PostgreSQL sequences provide non-reused, gap-tolerant document numbers.
- `stock_balances` is an atomic read projection; movements/FIFO remain
  reconcilable authorities.
- Sale-return cost comes from exact source allocations.
- Purchase-source lineage survives transfers and return restoration.
- Ledger/base amounts use fixed precision; no floating point.
- Oversized historical replay is blocked rather than partially applied.
- Old application rollback never reinterprets a quantity tenant as serial.

## Traceability Gate

Every SRS requirement family is assigned to:

- An implementation phase.
- An application/component owner.
- A public or tenant SQL owner where applicable.
- Mandatory test evidence.

Inclusive ID ranges in the matrix cover every individual ID in the range.
CI/CD, non-functional, integration, report, and test requirements have separate
sections.

## Tests and Validation

- Markdown/diff whitespace validation: passed.
- Required architecture section checks: passed.
- Requirement-family coverage review: passed.
- Provisioning/type-mismatch threat review: passed.
- FIFO/return/source-lineage walkthrough: passed.
- Backdating/locking/deadlock-order walkthrough: passed.
- Foreign partial-settlement journal walkthrough: passed.
- Rollback compatibility review: passed.

Phase 2 changed documentation and execution status only. It did not change
Python, SQL, migrations, Docker runtime behavior, routes, templates, or static
assets. The full Phase 1 two-tenant serial baseline therefore remains the
applicable runtime regression evidence:

- Comprehensive suite: all modules passed.
- SQL harness: 111/111 per tenant.
- Standalone HTTP: 66/66.
- Deep lifecycle: 2702/2702 per tenant.

## Exit Gate

All Phase 2 exit criteria are satisfied. Phase 3 — Public Company Metadata
Migration — may begin. Phase 3 must convert the approved logical public model
into additive, backward-compatible migrations and tests; quantity provisioning
must remain disabled until Phase 5.

