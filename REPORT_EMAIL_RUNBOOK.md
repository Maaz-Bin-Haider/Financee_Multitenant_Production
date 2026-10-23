# Company report emails

Phase 2 delivers the existing **Sale-wise Profit** report as HTML, plain text
and a CSV attachment. Figures come from `sale_wise_profit_json(day, day)`;
returned serials are excluded and confirmed draft sales are included by the
same SQL used on screen. Row percentages are markup on cost; the report total
is margin on revenue. Company currency is used, with at least the two decimal
places present in the source report. No GST columns or recalculation is added.

## Company setup

1. In the Financee admin, enable the company's **Report Email** feature and
   **Sales Reports → Sale-wise Profit**. Report Email starts off in new-company
   plans. Existing company registry rows are not rewritten by this release.
2. Give the configuring company member both **Can configure and send company
   report emails** (`auth.send_reports`) and **Can view Sale-wise Profit report**
   (`auth.can_view_sale_wise_profit`). Nothing grants these automatically.
3. As that member, open **Report Email**, save the sender mailbox and its app
   password, choose the company time zone and send time, then add recipients.
   Blank password means keep the existing password; the explicit clear box
   removes it. The password never comes back in settings/log responses.
4. Send a test, inspect its report and CSV, then enable daily delivery.
   Scheduled, manual and test deliveries have separate history. Manual/test
   sending uses saved settings and does not consume the day's scheduled slot.

Use a mailbox/app password dedicated to the company. Standard providers are
`smtp.gmail.com` and `smtp.office365.com`. An operator may set the comma-separated
`REPORT_EMAIL_SMTP_HOSTS` deployment variable to allow another provider. The
application accepts STARTTLS on port 587, or implicit TLS on port 465. It does
not use billing SMTP settings or a global report-mail password override.
Stored app passwords are part of tenant database backups; protect backups as
credentials. Existing billing/subscription email remains separate.

## Scheduling and failure handling

- The time zone defaults to `Asia/Karachi`. At or after the configured time,
  the worker sends **yesterday's** report, including an empty-day email when
  appropriate. Downtime is caught up later the same local day; older missed
  days require an explicit manual send.
- Every delivery rechecks company activity, provisioning, subscription, both
  company features, and the last mailbox-saving member's current active
  membership and both permissions. If that member loses authorization, another
  authorized member must save the mailbox again. Company suspension blocks
  delivery even for a platform operator.
- A tenant-specific database lock spans preparation and SMTP. An attempt is
  committed before contacting SMTP, so overlapping workers cannot both claim a
  scheduled day. A successful scheduled day is held across process restarts.
- Definite failures retry after 30 minutes, up to 12 attempts for that day's
  current schedule history. A crashed preparation becomes a retryable failure.
- A connection loss, partial recipient acceptance or crash during SMTP is
  **unknown**: some mail may have arrived. Automatic retries stop. Check the
  recipient inbox/server first, then re-arm deliberately. SMTP cannot provide
  an exactly-once guarantee after an ambiguous acknowledgement.
- Re-arming marks previous scheduled attempts superseded and adds an actor
  record; nothing is deleted. Only the current scheduled business day can be
  re-armed. It still waits for the currently configured time and authorization.
  Use manual sending for an older day. Logs include the original recipient
  list, date, trigger, outcome, currency and financial summary, never passwords
  or raw SMTP exception content.

## Worker deployment and rollback

`report_worker` uses the exact `WEB_IMAGE` used by web. Web alone runs public
migrations and tenant hardening; the worker starts after web is ready. It uses
`python manage.py run_report_scheduler`, with a 60-second tick and a heartbeat
health check. `REPORT_EMAIL_ENABLED=False` disables the feature's UI/endpoints
and delivery while allowing the worker to remain healthy.

The pull deployer stops the worker before replacing web and checks the matching
worker after HTTP/preflight checks. Worker failure rolls back the standalone
pull deployment as well. Phase 30 checks worker health and image equality and
restores both components on failure. When an older rollback image has no
report command, the worker remains stopped.

From `deploy/` on the intended production host:

```bash
docker compose -f docker-compose.yml ps web report_worker
docker compose -f docker-compose.yml exec -T report_worker python manage.py run_report_scheduler --health
# After restoring web to a chosen SHA, restore its worker (or keep it stopped
# if that older image has no report-mail command):
WEB_IMAGE=ghcr.io/maaz-bin-haider/financee-web:<approved-sha> bash report_worker_control.sh restore
```

Use the release controller for normal production changes. Stop the report
worker before manually checking out a repository version predating its Compose
service; old deployment scripts cannot manage an unknown newer worker.
Public migration history and tenant version remain unchanged (version 6).
The registered `tenancy/sql/add_report_email.sql` patch is included verbatim in
both the template and startup hardening. Applying it repeatedly preserves
configuration and history. Rollback leaves the additive tables intact.

Both encrypted DB/media and DB-only restore drills start/check a matching
worker when the image supports it and force report delivery off. They discard
inherited DB connection variables before loading the isolated restore env.
Do not enable restored schedules until the operator has reconciled recent
inbox/history state and deliberately accepted delivery from the restored estate.

## Local review

```bash
python3 deploy/review_stack.py start --project financee_review_email --port 8181 --mail-port 8182
python3 deploy/review_stack.py status --project financee_review_email
```

Application: `http://financee-review-email.localhost:8181/report-email/`.
Capture inbox: `http://financee-review-email-mail.localhost:8182/`.
Each review project has its own browser hostname, credentials, database,
volumes and internal application network. Only Nginx publishes loopback ports.
SMTP always goes to internal Mailpit in this review database, regardless of
mailbox settings. No real mailbox is needed. The helper's private temporary
`handoff.txt` records the exact image/commit and synthetic account password.
The old dark-mode review stack can remain open without sharing cookies.

Managers can configure/send; staff/read-only fixtures lack `send_reports`.
Alpha and Beta have distinct mailboxes/recipients, PKR/AED currency and
Karachi/Dubai time zones, with matching serials and document names. Both start
paused; browser verification may leave Alpha enabled with a delivered report.
Use only a separate regression project for destructive suites. The final
review record is `tests/PHASE2_REPORT_EMAIL_REVIEW.md`. No Phase 2 push is
permitted until the owner completes manual review and explicitly instructs it.
