# Phase 18 — Quantity Multi-Currency Results

Completed: 2026-07-26

## Delivered

- Quantity schema version 14 with immutable transaction-currency, exchange-rate,
  foreign-value, and base-value snapshots for purchases, sales, and lines.
- Manual foreign invoice rates; domestic documents remain fixed at rate 1 and
  do not accept conversion input.
- Durable supplier-payment and customer-receipt allocation records.
- Partial and final cash/bank settlements at manually entered settlement rates.
- Realized exchange gains and losses posted to accounts 4910 and 1990.
- Foreign returns valued at the original invoice rate and limited to the
  unsettled balance, so settled history is never rewritten.
- Open foreign invoice and realized gain/loss reporting.
- Purchase and sale currency selection, exchange-rate entry, settlement
  controls, and remaining-balance display.
- Explicitly no month-end unrealized revaluation.

## Verification

- Phase 18 focused integration: **23/23 passed**.
- Complete mixed-family suite: **31/31 modules passed**.
- HTTP suite: **70/70 passed**.
- System suite: **111/111 passed**.
- Deep serial lifecycle: **2702/2702 passed**.
- Production Docker image build and production-style entrypoint: passed.
- Django system checks, migration drift check, Python compilation, and
  whitespace validation: passed.

The exit gate passed: foreign party balances, the base ledger, cash/bank, open
foreign balances, and realized exchange gains/losses reconcile after partial
and full settlement, while serial-company behavior remains unchanged.
