# Phase 27 — CI/CD and ARM64 Results

Date started: 2026-07-27
Status: **IMPLEMENTED — EXTERNAL WORKFLOW RUN PENDING**

## Delivered

- Separate, diagnosable GitHub Actions jobs for:
  - serial regression;
  - complete quantity certification;
  - four-company isolation;
  - native ARM64 execution;
  - complete aggregate regression.
- Publication is blocked on static, serial, quantity, isolation, ARM64, and
  aggregate gates.
- The published release remains immutable-SHA pinned, multi-architecture
  (`linux/amd64`, `linux/arm64`), GHCR-hosted, and manual-production-approval
  gated.
- Every failed domain job uploads its own stack/container artifacts.
- `release_preflight` enumerates every active tenant and fails closed on
  provisioning state, registered/physical family mismatch, minimum version,
  missing required objects, safe report execution, or differing real schema
  fingerprints within a family.
- Pull deployment runs family/version/fingerprint/safe-report checks before
  and after deployment.
- Failed health checks still restore the previous image. The rollback path is
  now executable in a fast fake-runtime simulation.
- ARM64 smoke executes the real production image, public migrations, serial
  provisioning, quantity provisioning, mixed-family fingerprint checks, and
  the login HTTP endpoint.

## Local evidence

- Phase 27 release-contract checks: **11/11 passed**.
- Failed-health rollback simulation: passed and selected the previous image.
- Native Docker server architecture: `arm64`.
- ARM64 migration/provisioning/HTTP/family preflight: **5/5 passed**.
- Two independent serial schemas produced the same real object fingerprint.
- Quantity schema verified as family `quantity`, version 22.
- Phase 25 four-company isolation rerun: **17/17 passed**.
- Django system checks: no issues.
- Missing migration check: no changes detected.
- Shell syntax, Python compilation, Compose rendering, and diff whitespace
  validation passed.

## External T8 gate

The workflow definition cannot prove its own GitHub-hosted behavior before the
owner commits and pushes it. Phase 27 remains in progress until both are
observed:

1. a clean branch/pull-request run with all separate jobs and failure
   artifacts available;
2. a main push that executes the ARM64 gate, publishes both manifests, pauses
   at production approval, and exercises the SHA-pinned deployment path.

No commit or push was performed by the implementation agent.
