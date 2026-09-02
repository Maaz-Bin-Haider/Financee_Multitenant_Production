# Serial-Only Consolidation Phase 1 — Creation Freeze Results

**Execution date:** 2026-09-02

**Production target:** AWS EC2 `t4g.medium`, ARM64, `ap-south-1`

**Candidate tested:** uncommitted local working tree based on
`0f008141423890d5c69ca32ca7b6a3a6e92f8e4b`

**Production changed:** No

## Outcome

The Phase 1 candidate is locally ready for exact-commit protected CI/CD. New
Company rows are serial-only at every supported creation boundary and at the
PostgreSQL constraint. Existing serial schema version 6 and business behavior
were not changed.

Phase 1 is not complete: the candidate has not been pushed or deployed, and the
owner's required manual production verification remains pending.

## Implemented controls

- Company model choices contain serial only; model saves reject every
  non-serial value.
- The admin add/change form, company list, and filters expose no inventory-mode
  choice. A forged posted quantity field is ignored and the model default stays
  serial.
- `provision_tenant` exposes no `--inventory-mode` argument and assigns serial
  explicitly.
- Low-level provisioning and retry provisioning reject non-serial families.
- Migration `0008_serial_only_company_creation` first enumerates conflicting
  Company IDs and aborts before DDL. It then replaces the existing check with
  an exact `inventory_mode = 'serial'` database constraint.
- Active CI no longer creates quantity companies. Its focused replacement is a
  creation-freeze gate; ARM64 and concurrency gates now create serial tenants
  only.
- Legacy quantity runtime, routes, templates, and SQL remain untouched for
  Phase 2, except that the still-active entrypoint maintenance parser was
  deliberately decoupled from Company choices so startup remains compatible.

## Local automated evidence

| Gate | Result |
|---|---|
| Phase 0/1 and Phase 27–30 static/release contracts | **90/90 PASS** |
| Django system check | **PASS — 0 issues** |
| Migration drift | **PASS — no changes detected** |
| Serial regression matrix | **51/51 PASS, zero XFAIL** |
| Phase 1 live PostgreSQL creation freeze | **15/15 PASS** |
| Four-serial concurrent isolation/security | **16/16 PASS** |
| Active full production-stack suite | **20/20 modules PASS** |
| ARM64 container smoke | **6/6 PASS** |
| Encrypted backup/restore/old-image/rollback rehearsal | **PASS** |
| Production-like staging/UAT/capacity preflight | **PASS** |

The full suite included per-tenant serial party, item, purchase, sale, return,
cash, opening, equity, close, and report modules; 208 attachment checks; 40
subscription checks; 46 subscription-email checks; 77 feature checks; and 70
HTTP checks.

The recovery rehearsal produced a 1,003,552-byte encrypted database/media
bundle at `20260902T131738Z`, verified its checksum, rejected a corrupted copy,
restored it in isolation with a 43-second RTO, provisioned another serial
tenant, and proved the previous image
`4474d2a99be089c8d97c6640ffa29698577f3ff6` remains compatible with the forward
serial-only database. Total rehearsal time was 179 seconds; all disposable
Compose projects and volumes were removed.

The final staging run labeled the image
`local-working-tree-0f0081414238`, explicitly preventing uncommitted code from
being represented as an exact commit. Serial continuity was unchanged before
and after idempotent hardening, PostgreSQL/Redis health passed, and the
100-session connection/capacity preflight passed.

## Failure encountered and resolved

The first creation-freeze stack start failed before tests because
`apply_sql_all_tenants` inherited the newly serial-only model choices while the
Phase 1 entrypoint still performs no-op legacy quantity maintenance. No
production system was involved. The parser was separated from Company creation
choices, preserving the legacy runtime boundary until Phase 2. The corrected
container startup and every subsequent gate passed.

## Required next gates

1. Review and commit the exact Phase 1 diff.
2. Obtain explicit owner authorization before pushing to GitHub `main`.
3. Pass GitHub's exact-SHA checks, serial creation, serial isolation, ARM64,
   full regression, recovery, staging approval, image publication, and
   protected production deployment.
4. Owner manually verifies the real production system and records Phase 1
   PASS. Phase 2 remains blocked until that record exists.
