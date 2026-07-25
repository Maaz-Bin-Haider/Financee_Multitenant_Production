# Phase 6 — Accounting and Journal Foundation Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement from version 1 to version 2.
- Added an idempotent 17-account system chart of accounts:
  - Cash and Bank;
  - Accounts Receivable and Accounts Payable;
  - Inventory;
  - Sales Revenue and Cost of Goods Sold;
  - Owner's Capital, Opening Balance, and Retained Earnings;
  - Input Tax and Output Tax;
  - Inventory Adjustment Gain and Loss;
  - realized Exchange Gain and Exchange Loss;
  - Rounding Difference.
- Added journal headers and lines using base-currency `numeric(24,4)` amounts.
- Enforced non-negative amounts and exactly one positive debit/credit per line.
- Added deferred database constraint triggers that reject empty and unbalanced
  journals even when SQL bypasses the posting function.
- Added an atomic posting function with account validation, source-document
  uniqueness, and all-or-nothing failure behavior.
- Made posted headers and lines immutable.
- Added linked journal reversal with exact debit/credit inversion and duplicate
  reversal denial.
- Added account lookup and a reconciled trial-balance view.
- Added atomic formatted numbering per document type.
- Added the idempotent
  `tenancy/sql/quantity_accounting_foundation.sql` upgrade artifact and Docker
  startup dispatch for quantity tenants only.
- Expanded family verification to the accounting tables, functions, and
  identity sequences. Identity sequences are read through PostgreSQL
  `pg_class`, because `information_schema.sequences` omits them.

Parties, products, warehouses, inventory, FIFO, tax configuration, invoices,
payments, and reports remain in their assigned later phases. The quantity UI
therefore remains safely runtime-gated.

## Upgrade Evidence

The preserved Phase 5 mixed-family database contained:

- two serial tenants at serial schema version 6;
- one quantity tenant at quantity schema version 1.

Production startup:

- applied serial hardening and indexes only to the two serial schemas;
- applied the Phase 6 accounting artifact only to the quantity schema;
- upgraded that quantity tenant to version 2;
- completed family/version/fingerprint verification;
- started the production Gunicorn process successfully.

Repeated startup and the Phase 5 idempotency suite left exactly 17 accounts,
two distinct seed-registry rows, and no duplicate accounting objects.

## Focused Evidence

The Phase 6 suite provisioned two fresh quantity tenants and passed 39/39
checks covering:

- version and schema fingerprint;
- exact account seed and normal-balance classifications;
- lookup behavior;
- balanced posting and four-decimal precision;
- exact linked reversal;
- duplicate/reversal-of-reversal rejection;
- posted header/line immutability;
- empty, one-line, unbalanced, negative, both-sided, zero, and unknown-account
  rejection;
- direct-SQL empty and unbalanced journal rejection;
- duplicate source-document atomic rollback;
- zero-net trial balance and absence of invalid stored journals;
- sequential and 20-call concurrent numbering;
- unknown document-type rejection;
- independent document counters;
- independent tenant journals and matching account fingerprints.

Phase 5 quantity-foundation regression remained 28/28.

## Complete Regression Evidence

- Django system check: no issues.
- Missing-migration guard: no changes detected.
- Full mixed-family suite: all 19 modules passed.
- Serial system harness: 111/111 per serial tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: 2702/2702 per tenant; 5404/5404 total.

## Exit Gate

**PASS**

- Accounting seeds are deterministic and idempotent.
- Successful postings are non-empty, balanced, precise, and immutable.
- Invalid postings fail atomically without partial journal data.
- Reversals preserve a complete bidirectional audit trail.
- Trial balance reconciles to zero.
- Concurrent numbering is unique and tenant/document-type isolated.
- Existing serial accounting and transaction behavior remains unchanged.
- Phase 7 may begin.
