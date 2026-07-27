# Phase 29 Staging Acceptance and Security Runbook

Status: implementation complete; CI evidence and protected approval required

## Release candidate

Staging must run the exact immutable image SHA that passed CI. Rebuilding on
the staging host is not acceptable. Record the image tag and digest before
acceptance begins.

`tests/phase29_staging_acceptance.sh` builds the checked-out release candidate
once, labels and tags it with `GITHUB_SHA`, starts an isolated production-like
Compose stack, and rejects the run unless the web container image ID exactly
matches that candidate. It uploads image provenance, test logs, container
state, stack logs, the T7 result, and a machine-readable acceptance summary.

## Staging data

- Restore only a sanitized Phase 28 recovery bundle.
- Use a separate Compose project, credentials, hostname, database, media
  volume, and Redis namespace.
- Verify every restored serial tenant with `release_preflight`.
- Provision two synthetic quantity tenants after restoration.
- Never copy production passwords, session data, API credentials, mail
  credentials, or backup passphrases into staging.

The automated CI environment uses synthetic-sanitized data and depends on the
successful Phase 28 encrypted recovery gate. An organization using a sanitized
production-derived bundle must perform the same run in its private staging
environment; such a bundle must never be committed or uploaded as a public CI
artifact.

## Mandatory review areas

1. Tenant isolation and persistent-connection search-path reset.
2. Route, feature, subscription, and object-level authorization.
3. Private attachment metadata, preview, download, guessed-ID, and traversal
   behavior.
4. SQL identifier validation and hostile serial/quantity payload rejection.
5. Company provisioning, schema-family verification, and inventory-mode lock.
6. HTTPS proxy handling, secure cookies, CSRF, response headers, and redacted
   error responses.
7. Dependency integrity and vulnerability findings.
8. Wholesaler purchase, sale, return, transfer, count, settlement, attachment,
   audit, dashboard, report, CSV, and Excel acceptance.
9. Health checks, logs, rate limits, backup evidence, rollback, and operator
   alert visibility.

## Approval record

The exit gate requires recorded product-owner, engineering, and operations
approval of one exact release image. Any open P0/P1 finding blocks approval.
The final evidence must include staging URL/environment identity, image digest,
test commands, sanitized-data provenance, findings and resolutions, and named
approvers.

The `staging-release-approval` CI job uses the protected
`staging-release-approval` GitHub environment and blocks image publication.
Configure its required reviewers to include the product owner, engineering,
and operations owners. The GitHub environment approval history is the
authoritative named approval record.

## Automated execution

Run:

```bash
PHASE29_ARTIFACT_DIR=phase29-artifacts \
  tests/phase29_staging_acceptance.sh
```

The gate covers:

- production settings and runtime hardening;
- T4 serial regression and T5 quantity workflow/report UAT;
- T6 two-serial/two-quantity isolation, authorization, attachment, cache,
  search-path, and error-scrubbing behavior;
- selected T7 capacity and concurrency smoke;
- T8 as an enforced upstream encrypted recovery gate;
- initial/final all-tenant release preflight and Redis health.

Local validation on 2026-07-27 passed: security contracts 18/18, runtime
hardening 5/5, serial 51/51, quantity 20/20, mixed-family isolation 17/17,
selected T7 at 1,000 SKUs, 20,000 movements, and 20 concurrent sessions with
zero failures, deadlocks, negative stock, or waiting locks.
