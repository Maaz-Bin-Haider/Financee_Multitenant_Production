# Phase 20 — Quantity Platform Controls Results

Completed: 2026-07-26

## Delivered

- Quantity schema version 20 with shared private attachment metadata.
- Image/PDF upload, replacement, preview, download, and reversal cleanup for
  quantity purchases, sales, purchase returns, and sale returns.
- Quantity-aware document-table resolution without changing serial mappings.
- Feature-disabled and permission-denied upload/API enforcement.
- Smart descriptions on all four quantity transaction screens.
- Immutable audit events for quantity masters, document headers and lines,
  FIFO/inventory state, journals, taxes, settlements, financial modules, and
  attachment changes.
- Permission-gated audit page and JSON endpoint.
- Type-aware quantity feature catalogue and direct-route middleware guards.
- New audit-view and attachment-management permissions.
- Existing shared subscription active, grace, blocked, and suspended controls
  verified against direct-route bypass attempts.

## Verification

- Phase 20 focused integration: **19/19 passed**.
- Shared attachment suite: **104/104 passed**.
- Feature-flag suite: **77/77 passed**.
- Subscription suite: **40/40 passed**.
- Quantity foundation: **29/29 passed**.
- Quantity financial regression: **27/27 passed**.
- Complete mixed-family suite: **33/33 modules passed** after updating the
  Phase 19 schema-version expectation.
- HTTP suite: **70/70 passed**.
- Serial system harness: **111/111 passed**.
- Deep serial transaction lifecycle: **2702/2702 passed**.
- Docker build, fresh quantity provisioning, public migration, Python
  compilation, Django startup, and whitespace validation passed.

The exit gate passed: shared controls are enforced for quantity tenants at the
UI, HTTP, permission, feature, subscription, storage, and database layers while
serial behavior remains green.
