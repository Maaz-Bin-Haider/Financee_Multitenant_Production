# Phase 0 Serial-Only Discovery and Test-Tenant Retirement Results

**Date:** 2026-09-01

**Production platform:** AWS EC2 `t4g.medium`, ARM64, `ap-south-1`

## Source and workflow evidence

- Phase 0 discovery source: `8f407dea9e488eab8980b48309c064a00db714cd`.
- Guarded retirement workflow source:
  `7bed3bcfb4b0536421eda83b80e065c88d6689eb`.
- Initial CI/CD run: `33532428404`. Every build/test/recovery/staging/image
  job passed. The deployment stopped before deployment because its read-only
  serial-only guard detected registered quantity tenant `tenant_company_2`.
- No container replacement, migration, tenant SQL replay, or Phase 1 behavior
  change occurred in that stopped deployment.

## Owner classification and admin action

The owner classified Company ID 2 as test-only and deleted its Company row
through Django admin. Django cascaded the public Company relationships but, as
the source has no Company `post_delete` schema handler, did not drop the
physical PostgreSQL schema.

## Read-only production inspection

Workflow run `33535199430` passed at source
`bae06dec74399df536176d8fa67188bb74225974` and proved:

- Company ID 2 registry rows: `0`.
- Registry references to `tenant_company_2`: `0`.
- Physical `tenant_company_2` schemas: `1`.
- Family: quantity, version `22`.
- Size: `4,087,808` bytes across `54` base tables.
- Registered companies: `1`, active: `1`, inactive: `0`.
- Remaining registered tenant: serial family, version `6`, ready.
- Remaining serial journal: balanced; no unbalanced schema reported.
- Before retirement, Phase 1 readiness was false only because
  `tenant_company_2` was an invalid orphan quantity schema.

The earlier inspection run `33534903662` failed before repository pull,
Docker, or database access because empty optional SSH arguments were not
preserved. The corrected workflow added a regression contract for that case.

## Backup-first retirement

Protected production workflow run `33535608469` passed at source
`7bed3bcfb4b0536421eda83b80e065c88d6689eb`:

1. Re-proved Company 2 absent, no registry reference, and the physical target
   as unambiguous quantity family.
2. Started the root-owned production database backup service.
3. Created release `db-backup-20260901T170630Z` after the operation began.
4. Independently verified the encrypted upload and reported it fresh at age
   13 seconds.
5. Re-checked the timestamp before permitting destructive SQL.
6. Dropped only `tenant_company_2` inside a PostgreSQL transaction; PostgreSQL
   reported `DROP SCHEMA` followed by `COMMIT`.
7. Proved no physical schema or registry reference remained.
8. Passed strict Phase 0 serial-only discovery with continuity evidence.
9. Passed `release_preflight --require-family serial` on the running web image.
10. Passed the local production login-page HTTP check.

The private backup release was independently re-queried after the operation:

- Encrypted database asset:
  `financee-db-20260901T170630Z.dump.tar.enc`, `1,167,392` bytes, uploaded.
- Ciphertext checksum asset:
  `financee-db-20260901T170630Z.dump.tar.enc.sha256`, `108` bytes, uploaded.
- Release is published, not a draft, and not a prerelease.

EC2 evidence directory:
`retirement-evidence/company-2-20260901T170628Z`.

GitHub retained operation artifact: `company-2-execute-evidence` on run
`33535608469`, retained for 90 days.

## Independent public health check

After retirement, `https://financee-swisstech.com/` redirected to
`/authentication/login/`, titled `Login | Financee`, and rendered the expected
username, password, password-visibility, and sign-in controls.

## Remaining gates

- The owner must manually verify the real serial production workflow after
  this change and record an explicit Phase 0 PASS.
- The fresh recovery release has passed encryption, checksum, remote download,
  and PostgreSQL archive-catalogue verification. An isolated restore of the
  current production recovery point remains open and must pass before Phase 1.
- No test-user account is deleted by deleting a Company row; any orphan user
  account cleanup is a separate identity review and is not authorized here.
- Phase 1 has not started.
