# Company Team Activity

Team Activity shows company work on the same contribution scale as Accounting:
0, 1–4, 5–10, 11–25 and 26+ actions. It includes year/day views, work mix,
weekday/hour distribution, team comparisons, a watch list, PDF and CSV exports.
Sessions are displayed separately and do not count as work. Dates/hours use the
explicitly labeled `ACTIVITY_TIMEZONE` (default `Asia/Karachi`).

Enable the company's `team_activity` feature and grant `auth.view_team_activity`
to its manager. This permission is seeded idempotently, never auto-granted.
New-company plans start with the dashboard off; existing lists are not rewritten.
`TEAM_ACTIVITY_ENABLED=False` disables access; `TEAM_ACTIVITY_RECORDING_ENABLED=False`
disables collection independently. Disabling the manager screen does not discard
ordinary staff work/session events. Other source-screen permissions and company
switches still govern record links and exports.

Each tenant owns its append-only `activity_events` table. Update, delete and
truncate are refused. User IDs are not foreign keys to auth: legitimate event
snapshots remain after an actor leaves. Current members come only from that
company's membership; former members use local event snapshots, never their
current foreign-company profile. Unknown failed-login names are not assigned to
any company. Labels contain action/record references, not financial amounts,
contact details, descriptions, credentials or request bodies. Session addresses
are connection peer addresses; forwarded client headers are not trusted.

The tenant patch `add_team_activity.sql` is registered and included verbatim in
the template/startup hardening. Version remains 6; public migrations, posting
SQL and report calculations are unchanged. Reapplying preserves all history.
There is no new worker. Recording failures are best effort and cannot abort
successful business transactions. Rollback to an older image leaves the added
history intact and stops collection from code that predates this feature.

## Historical import

No import runs at startup, during rollout or in a migration. An operator can
preview **one** active company with an explicit past, timezone-aware cutoff:

```bash
python manage.py backfill_team_activity --company <id> --cutoff <aware-ISO-timestamp>
```

Execution additionally requires `--execute --confirm tenant_company_<id>`.
Never run against production without separate owner authorization. For example,
choose the cutoff deliberately before enabling live collection and retain its
preview/output as release evidence. This phase authorizes only disposable/local
verification, not a production historical import.

The command derives one approximate entry per supported attributed legacy
record, at local noon on its business date. It does not invent deletes, edits,
sessions or original creation timestamps. Legacy Entry By may reflect the last
editor. Unknown/nonmember attribution is skipped instead of joining foreign
accounts. Already observed live records are skipped; stable source keys and a
unique backfill index prevent duplicates on reruns. Importing reads business
records and inserts audit events only; financial documents/journals are unchanged.

## Reports and exports

Only successful JSON report data responses count as runs; opening HTML,
lookups and automated dashboard refreshes do not. Repeated identical route and
filters within 60 seconds count once. Cash forms record directly after their
successful SQL/attachment operations; failed/denied submissions do not count.

PDF/CSV/Excel files are built in the browser. Their notifications are explicitly
`source=browser`, not server-confirmed downloads. A signed ten-minute receipt
binds the source to the current user/company/session. The endpoint rechecks
source and export permissions/features, accepts no actor or arbitrary label,
limits frequency, and deduplicates repeated notifications for five seconds.
A failed/offline/expired notification never blocks the user's download. Audit
collection is therefore best effort rather than guaranteed delivery.

Watch rules cover live deletions, updates with a captured document date more
than 30 days old, work before 09:00 in the configured zone, and three failed
sign-ins within ten minutes. They are investigation prompts, not conclusions
about misconduct. Imported approximate history is excluded from those rules.
Day lists show at most 1,000 events and state when truncated; watch lists cap
at 500. Queries have statement timeouts and request rate limits.

## Local owner review

Use the standalone `review_stack.py` helper and a separate `financee_review_activity`
project. Never run mutating suites against its manual review database. Fixtures
are synthetic and capture all SMTP internally. Earlier feature review projects
and Accounting remain untouched. See `tests/PHASE4_TEAM_ACTIVITY_REVIEW.md` for
actual verification results, exact image handoff and the owner checklist.
