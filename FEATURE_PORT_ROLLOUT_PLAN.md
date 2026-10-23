# Financee feature rollout plan

Created: 2026-10-23. Status: Phase 1 deployed and owner-confirmed; Phase 2 implementation authorized. Phase 2 push and later phases remain gated.

## 1. Scope and working agreement

Port these four capabilities from Accounting Plus Inventory into Financee Multitenant:

1. Dark mode matching Accounting's appearance and behavior, including dark as the default when no preference is saved.
2. Scheduled report emails.
3. Spotlight search.
4. Team Activity.

Financee is the only repository to modify. `/Users/swisstech/Development/Accounting-Plus-Inventory-System` is a read-only reference. Do not edit its files, run its mutating setup/test scripts, change its branches, commit there, or operate its deployment.

The owner requires small, meaningful commits throughout implementation, an isolated local running system after each completed feature, manual owner verification, and an explicit instruction before any push. Do not implement all four features in one uninterrupted batch. Do not start the next feature while the current feature is waiting for review or release approval.

The owner instructed "start" on 2026-10-23, authorizing Phase 1 implementation. Later feature phases still require the preceding manual review/push/release gates.

### Baseline and branch

- Financee remote main and latest successful deployment verified on 2026-10-23: `7a0e6af5335047b6e1596edfd23eb3a3f7f5f178`.
- Implementation/planning branch: `codex/financee-feature-rollout`, created from local `main` at that commit.
- Existing `feature/dark-mode` at `6e4fe68d4def6b4ab0b55f1d32a4f85639881c58` is preserved. It contains a substantial partial port, but defaults to light. Reuse its work through focused commits and adapt it to this request; do not overwrite, reset, amend or delete the original branch/commit.
- Do not rewrite the owner's previous history, squash the feature work, manufacture empty commits, or change commit dates. Keep an understandable history of actual changes and fixes.
- Do not fetch-and-merge unrelated changes automatically. Before each feature, inspect local/remote/released versions and resolve the intended base deliberately.

### The stop point after every feature

1. Finish that feature in small local commits, including related tests, SQL rollout registration, required contract pins and documentation.
2. Run the automated feature/isolation checks and applicable production-stack regression gates in disposable resources.
3. Build and start that exact committed version in its isolated local review stack. Leave it running for the owner.
4. Give the owner the local URL, synthetic test accounts, feature switches, a short manual checklist, commit list, and automated test results. Keep credentials in the local review handoff, not committed source.
5. **STOP.** Do not push, merge, deploy, start the next feature, destroy the review stack or reset its data while the owner is checking it.
6. If the owner reports an issue, fix it in another focused commit, rerun affected checks and return to the same review stop point.
7. Push only when the owner explicitly instructs it. Local review approval alone, silence, elapsed time or a green test run is not push authorization. Confirm the authorized branch/destination from the instruction before acting.
8. Follow the repository's protected CI/release process. A branch push is not production deployment approval. Do not bypass GitHub staging/production gates or self-approve production. Observe the applicable CI/release result before beginning the next feature; if an owner-controlled approval is pending, report it and wait.

## 2. Shared technical rules

### Preserve Financee's architecture

- Companies remain isolated PostgreSQL schemas. The authenticated user's Membership determines the tenant; request-supplied company/schema IDs never select another company's data.
- Shared Django auth/users/permissions remain in `public`; business/report/email/activity data belongs to the appropriate tenant schema.
- Preserve request-scoped search-path activation/reset and thread-local Gunicorn connections. Background work must enter and leave a validated tenant scope explicitly, including every exception path.
- Preserve subscriptions, per-company switches and existing endpoint/action permissions. A hidden menu is not an access control.
- Do not introduce the retired inventory-mode/quantity/FIFO family, GST, Stock Tracker, a workspace chooser, or a general frontend modernization as incidental dependencies of this request.
- Preserve existing create/update/delete accounting and serial rules. Reuse the existing report functions and ordinary document posting functions.
- Use Financee's `Alerts` layer and semantic theme tokens. Adapt the source project's differing routes, permission names, cash-party markers and payload shapes rather than copying them blindly.

### Tenant SQL and permission rollout

For each additive SQL feature:

1. Create a registered, idempotent tenant patch.
2. Include it in the new-company template and existing-company startup hardening in a controlled, testable way. Preserve the bootstrap/recovery contracts; do not edit the old bootstrap just to append a new feature when startup hardening already supplies it.
3. Verify a fresh bootstrap, a freshly provisioned company, an upgraded company and repeat application.
4. Keep required schema version 6 unless a documented compatibility requirement makes a version change necessary; a bump also needs a deliberate Phase 3B reversal strategy.
5. Use idempotent `post_migrate` permission seeding, following the draft app's pattern, without new audited migration-history rows or company-row writes. Test the real startup path, not only a management shell.
6. Update Phase 2 source/SQL/UI pins for each intentional change in the same commit, retaining independent accounting invariants. Do not disable or broadly weaken the historical gates to make a port pass.
7. Check the Phase 30 before/after audit against additive tables and any intended historical backfill. Release continuity and old-image recovery must remain explicitly proven.

New company feature-plan defaults: put Report Email, Spotlight and Team Activity in the explicit disabled-by-default plan and allow the platform operator to enable them. Existing company JSON lists retain their current semantics and are not silently rewritten during startup. Existing companies may therefore see the new feature as available to authorized users; no new permission is auto-granted. Report delivery remains off until a company configures and enables its schedule. Test and document both cases.

### Local isolation and manual review

Build a dedicated review Compose configuration and helper commands as the first implementation increment of Phase 1. Use Financee's production image/entrypoint, with local resource limits, instead of a separate simplified application.

- Unique project per feature, e.g. `financee_review_darkmode`, `financee_review_email`, `financee_review_spotlight`, `financee_review_activity`.
- Explicit project-scoped volumes and networks; no external/shared volumes, fixed container names, host production paths, production env files, production credentials or existing company dumps.
- Publish only on loopback. Suggested application URL: `http://127.0.0.1:8180`; choose an available port without stopping another stack. Database and Redis need no host port.
- Generate local-only configuration outside the build context or in correctly ignored paths. The helper refuses production-looking project names and requires an exact project match before cleanup/reset.
- Create at least two synthetic companies with different users, permissions, subscriptions, currencies and feature settings. Deliberately reuse names, serials and document numbers across the schemas to expose leakage.
- Provide a platform operator, company A manager/staff/read-only users, and company B manager/staff users. Include denied/disabled cases and representative sale/purchase/return/draft/cash-flow records.
- Add a local mail capture service for the email feature. Disable Financee's existing real subscription-email delivery and all external report delivery in automated/review fixtures; test messages go only to the local capture inbox.
- Automated tests use separate disposable projects. Keep the manual review project/data stable until the owner finishes checking it.
- Each completed feature's handoff identifies the exact reviewed commit and image. Later fixes require a refreshed handoff; a changed tree is not the same reviewed build.

## 3. Phase 1 — Dark mode parity

**Outcome:** Financee has the same dark-theme appearance and interaction pattern as Accounting, adapted to Financee-only screens. A new browser starts dark; an explicit saved light preference remains light.

### Implementation increments / intended commits

1. `Add an isolated Financee review stack and synthetic company fixtures` — safe setup/start/stop helpers, loopback routing and reproducible accounts/data. Verify coexistence without modifying Accounting or any existing Docker project.
2. `Restore Financee theme tokens and the pre-paint theme switch` — reuse the preserved dark-mode branch selectively; synchronize head/body/login/suspended-page checks; default to dark; handle unavailable localStorage, persistence and cross-tab synchronization.
3. `Match Accounting dark styling across Financee transaction screens` — purchases, sales, returns, drafts, parties, items, cash-flow screens, lookup/history popups, alerts and smart descriptions. Split into smaller screen-group commits as necessary.
4. `Complete dark styling for Financee reports and company modules` — Sales Reports, opening stock/cash, owner equity, month close, attachments and subscription surfaces. Preserve readable exports/print and fixed PDF colors; keep admin behavior aligned with the reference's separate admin treatment.
5. `Verify theme parity and document Phase 1 review` — focused behavior/asset checks, required byte pins, browser checks, regression results and review instructions. Related tests/pins accompany their implementation commits, not only this final record.

### Automated and manual acceptance

- First visit, reload, login/logout, switch to light and back, second-tab synchronization, missing storage and no initial bright flash.
- Desktop, narrow/mobile views, dropdowns, history windows, descriptions, alerts, draft screens and every Financee-only module.
- Tables, inputs, disabled/error states and chart readability. Screen captures compared with the reference where screens correspond; do not copy another product's navigation just to match a screenshot.
- PDFs and printed reports retain their intended export treatment in either browser theme.
- Full Financee suite plus relevant serial/UI/recovery compatibility contracts remain green.

**Gate 1:** leave the isolated dark-mode build running, provide the checklist and commits, and wait for the owner's manual review and explicit push instruction. No report-email work before this gate is released.

## 4. Phase 2 — Company-scoped report emails

**Outcome:** each company can configure its own report sender, recipients, delivery time, manual send, delivery history and re-arming, with no cross-company configuration or report access.

### Important adaptation

Accounting emails a GST-aware Sale-wise Profit report using `sale_wise_profit_report` and hardcoded AED presentation. Financee instead has `sale_wise_profit_json` and `vw_sold_serial_profit`, without the GST columns. Email Financee's existing Sale-wise Profit data, matching the screen's figures; use the company's currency and omit unavailable GST columns. Do not add GST or alter accounting calculations as a prerequisite. Exact source-column/summary mapping is documented and tested before building the email renderer.

### Implementation increments / intended commits

1. `Add tenant report-email settings recipients and delivery history` — registered idempotent SQL patch, constraints/indexes, SQL read/write functions, template/hardening integration, permission seeding and company feature switch. Settings/recipients/logs stay inside each tenant; passwords never appear in read APIs or logs. A process-wide app-password override must not accidentally configure every company's mailbox.
2. `Adapt report-email payloads to Financee sales data and currency` — reuse the report source, explicit Decimal/rounding handling, HTML/text/CSV generation, company branding, empty-day behavior and escaped content. Preserve the source project's Financee-compatible behavior without its GST/AED assumptions.
3. `Add report-email settings recipients and delivery screens` — mailbox/schedule status, recipient management, logs, test/send-now and re-arm controls; permissions and feature checks on every endpoint. Financial report access must also be authorized, not inferred from a menu link.
4. `Add a tenant-aware report delivery worker` — a dedicated Compose worker using the same SHA-pinned application image and a management-command loop, started after web/schema readiness. Explicitly enumerate eligible companies, establish/reset tenant scope, isolate failure of one company, and use tenant-specific locks/claims. Update pull-deploy, Phase 30 health checks, review stacks and recovery paths to start/check the worker. Rollback must restore the matching worker image, or stop it when returning to an older image without the command; do not leave a new worker serving an old web release. Do not assume a newly declared service will be started by existing web/nginx-only deployment commands.
5. `Protect scheduled reports against duplicate and stale delivery` — per-company business day/timezone (default Asia/Karachi), retry spacing/limits, worker-restart recovery, clear delivered/failed status, historical re-arm logs and schedule revalidation. Subscription suspension, company inactivity, revoked feature access and invalid sender authorization prevent background delivery.
6. `Verify company email isolation and document Phase 2 review` — concurrent scheduler tests, report totals/currency reconciliation, fresh/upgrade/repeat SQL checks, full regression, deployment-worker lifecycle and rollback evidence. Browser preview uses only the local mail capture service.

### Acceptance

- Company A and B have different recipients, sender settings, currency and schedules. Each email and delivery log contains only its own company's report.
- A failure in A does not stop B; retries and duplicate claims do not create duplicate scheduled messages across workers.
- Manual sending, scheduled sending and re-arming retain their distinct behavior. An SMTP disconnect after acceptance is an ambiguous outcome: do not promise exactly-once SMTP delivery; document the retry/reconciliation behavior and preserve attempt evidence.
- Disabled/subscription-blocked companies and unauthorized users cannot send or read report configuration. Secret fields are write-only/masked; existing subscription notifications remain independent.
- The email report reconciles with Financee's on-screen Sale-wise Profit for normal sales, draft conversions, returns and no-sales days. No journals, stock or balances change.
- Local inbox access, test recipients, schedule examples and a manual review checklist are handed to the owner. No real mailbox send is required for automated/manual local acceptance.

**Gate 2:** stop with the isolated email system and capture inbox running; wait for manual review and explicit push instruction. No Spotlight work before this gate is released.

## 5. Phase 3 — Tenant-aware Spotlight search

**Outcome:** the Accounting-style search palette finds Financee's permitted pages, parties, items, serials, documents, quick actions and recents, and opens the right existing screen.

### Important adaptation

Accounting's Spotlight depends on its earlier lookup and record-link work. Financee lacks that infrastructure, and some route names/permissions/report pages differ. Port the necessary read/search/ID-resolution/link helpers within this feature; a wholesale rewrite of every existing entry-form picker is outside scope. Source schemas use `is_system`; Financee uses `is_cash`. Every query must use the active tenant, and page visibility must respect Financee's company feature plan as well as user permissions.

### Implementation increments / intended commits

1. `Define Financee search capabilities and safe record links` — inventory supported routes, document read-by-number permissions, serial field-level visibility and report entry points. Add guarded deep links for documents/parties/items/reports, read once per navigation. Unknown/deleted targets leave the current screen stable and show its normal feedback.
2. `Add tenant-scoped Spotlight queries and record resolvers` — parameterized bounded queries, escaped wildcard handling, appropriate indexes, duplicate-name behavior and strict IDs for new links/actions. No business posting-function signature changes.
3. `Add the Spotlight palette and permitted page registry` — sidebar/mobile trigger, Cmd/Ctrl+K and `/` outside text fields, keyboard navigation, Escape/focus return, loading/error/empty states, light/dark styling and accessible mobile layout.
4. `Add party item serial and document search results` — grouped/ranked results, permission-limited balances/prices, draft reservations only for eligible viewers, document kind/number disambiguation, bounded paging and escaped highlighting. Include Financee modules and already-released Report Email; exclude nonexistent GST/workspace/profit routes.
5. `Add safe quick actions and company-scoped recents` — opening/prefilling existing forms only; never post transactions from search. Namespace browser storage by user and company, clear or isolate it across sign-out/account changes, and revalidate recents against current permissions/features before display/opening.
6. `Verify Spotlight security performance and manual flows` — same-name/same-number tenants, cross-company ID probes, denied field visibility, disabled features, stale responses, logout/login switching, keyboard/mobile checks, representative query measurements and full regression.

### Acceptance

- Two companies with identical party names, serials and document numbers see only their own results and links.
- Restricted users cannot infer purchase cost, sale price, balances, serials or reservations from a broader search permission.
- Switching a module/report off removes its pages/results/actions/recents and blocks direct access. Sending a crafted company/schema ID cannot change the query scope.
- Selecting a result opens the correct record; quick actions prefill the correct allowed form without writing anything.
- Query cancellation/out-of-order responses cannot expose another session's results. Recent searches never bleed between companies/users sharing a browser.
- Palette, deep links, report entry points and no-result cases work in both themes and from the keyboard.

**Gate 3:** stop with the isolated Spotlight build running; wait for manual review and explicit push instruction. No Team Activity work before this gate is released.

## 6. Phase 4 — Company-scoped Team Activity

**Outcome:** an authorized company manager sees Accounting-style contribution grids, day details, work mix/hours, team comparisons, watch list and exports for their company's users only.

### Important adaptation

The source queries enumerate all `public.auth_user` rows. Copying that into Financee would expose users from other companies. Company membership must constrain user selection, detail endpoints, comparison/watch queries and any auth joins; company-local event snapshots preserve legitimate historical actor labels. This feature is separate from the existing opt-in platform-admin activity report and does not grant company managers platform-wide visibility.

### Implementation increments / intended commits

1. `Add a tenant append-only activity log and manager access` — registered idempotent SQL, indexes, immutable-event triggers, permission seeding and feature integration. Manager access and event recording are separate: a staff member can generate legitimate work events without permission to read team analytics.
2. `Record successful Financee business actions in tenant activity` — parties/items, purchases/sales/returns, cash flow, drafts/conversions/returns and Financee-only opening/equity/close actions where supported. Record only successful actions, preserve actor snapshots, and keep audit failures from turning successful saves into errors or contaminating database transactions. Split by workflow group into focused commits.
3. `Record report use exports and company session events` — accurate successful-run classification, browser PDF/CSV/Excel notifications with permission/feature checks and bounded deduplication. Resolve sign-in/sign-out/known-user failures to a verified membership even before/after authentication; anonymous unknown-name attempts remain in platform logs, not assigned to an arbitrary company's team. Reset schema scope on every path.
4. `Add a controlled historical activity backfill` — derive approximate history from each tenant's own Entry By/document timestamps, with explicit cutoff, deduplication and rerun safety. Do not fabricate edits/deletes or claim approximate rows are live observations. Unknown/nonmember actor IDs must not disclose another company's account details.
5. `Add the company manager activity dashboard and exports` — shared intensity thresholds (0 / 1-4 / 5-10 / 11-25 / 26+ work actions), year/day navigation, team comparison, hours, watch list, PDF/CSV, theme/mobile/keyboard treatment, and links using the released Spotlight infrastructure. Session events are separate from work; approximate history remains labeled.
6. `Verify activity isolation continuity and release compatibility` — managers cannot select another company's user ID; forged export events cannot impersonate another actor; successful/failed actions are counted correctly; immutable events resist update/delete/truncate; fresh/upgrade/repeated rollout and query performance pass; all previous features and accounting flows still work.

### Backfill and release continuity decision

The Phase 30 controller compares tenant data before/after deployment. Creating empty additive tables fits the existing pattern, but inserting historical activity during startup changes row counts and fingerprints. Do not hide or globally exclude this new table just to pass the audit. Introduce the empty log through normal additive deployment, then run an explicit, narrowly scoped, authorized backfill step with its own preview, evidence, idempotency and accounting-before/after checks. The local review includes realistic approximate history; the production backfill remains a separately described release action.

The append-only table also affects generic cleanup/TRUNCATE helpers and recovery fixtures. Update only disposable fixture/reset paths deliberately; do not weaken production immutability to let tests reset data.

### Acceptance

- Company A managers see A users/history only; B managers see B only. Ordinary staff cannot open manager endpoints directly.
- Creates, edits, deletes, conversions, releases, reversals, report runs and exports are represented appropriately; failed document actions do not count as successful work.
- Browser events are evidence of a browser-reported export, not a guarantee that a file reached disk. Backfilled history is explicitly approximate, never a reconstructed perfect audit trail.
- Existing platform operator/admin behavior remains separate and intact; no company-wide permissions are auto-granted.
- Backfill neither modifies invoices/journals/stock nor duplicates events on rerun. Feature disabling hides analytics and preserves historical records.
- Ordinary recording continues when the company Team Activity analytics switch is off, preserving the audit history for later authorized use. The analytics switch governs the page, read APIs and analytics exports, not the successful business actions being observed. Browser export recording still verifies the exported source report's feature and permission.
- Event links obey the target screen's current permission/feature policy; a manager's activity access does not grant access to every underlying financial document.

**Gate 4:** stop with the isolated Team Activity build running; wait for manual review and explicit push instruction. No automatic final merge, deployment approval or production backfill.

## 7. Commit and evidence policy

Every meaningful implementation increment, correction and review fix gets a descriptive local commit. A tightly related implementation/test/SQL-registration/contract-pin set is one coherent change; do not leave known broken contract pins in an intermediate commit simply to increase the count. Larger increments above should be split by schema, service, endpoint, UI or workflow group when those pieces can stand coherently.

Before committing: inspect the diff, run appropriate targeted checks, and stage exact files. Never commit real secrets, production exports, generated static trees, Docker volumes, browser artifacts, temporary env files or unrelated work. Never stage Accounting files.

Maintain `PROJECT_CONTEXT.md` with completed decisions and `FIXED_ISSUES.md` for diagnosed fixes. Preserve exact documentation-contract sentences. Add one result/review record per feature containing:

- Source reference commit, Financee starting/ending commits and change list.
- SQL/template/hardening/permission/feature-switch changes and fresh/upgrade evidence.
- Automated results, isolation/permission coverage, known limitations and rollback behavior.
- Exact local URL/image/commit, synthetic account roles and manual test steps.
- Owner review feedback, fix commits, explicit push authorization and subsequent CI/release evidence as they occur.

GitHub will receive these commits only after the owner's authorized push. No contributions, remote updates or production status are claimed merely because local commits exist.

## 8. Current checkpoint

- [x] Review both existing projects and verify their latest recorded releases.
- [x] Preserve the existing dark-mode branch and create a local rollout branch from main.
- [x] Write the phased plan and persist the owner's review/push boundaries.
- [x] Phase 1: isolated environment plus dark-mode parity, automated checks, owner review, authorized push/release.
- [ ] Phase 2: report emails, automated checks, owner review, authorized push/release.
- [ ] Phase 3: Spotlight, automated checks, owner review, authorized push/release.
- [ ] Phase 4: Team Activity, automated checks, owner review, authorized push/release; separately authorized production backfill where needed.

Phase 1 checkpoint: Phase 1 is implemented, committed and verified locally;
the owner reported manual review passed on 2026-10-23 and explicitly instructed
the branch push and CI monitoring.
See `tests/PHASE1_DARK_MODE_REVIEW.md` for results and the manual checklist.
Branch push `41c8151` completed and CI run `39970474964` passed all 13 test
gates. The owner subsequently authorized merging to `main` before Phase 2.
Preserve the implementation commits with a fast-forward merge, push `main`,
and watch its workflow. Leave the isolated review stack running and protected
staging/production approvals to the owner. Do not start Phase 2 while the
preceding release gates are pending.

The owner subsequently confirmed Phase 1 works in production and authorized
Phase 2. Main `da30168` and workflow `39972044447`, including production deploy,
are successful. Implement report emails locally on `codex/report-emails`.
Gate 2 still requires manual review and a new explicit push instruction.
