# Financee — Full Deployment + CI/CD Guide (fresh EC2)

Step-by-step, from a brand-new Ubuntu EC2 instance to a running production
stack with automated, approval-gated deploys from GitHub Actions and a daily
encrypted database backup.

*Last checked against the repository: 2026-09-26.*

Written for this concrete setup (adjust if yours differs):

- **Instance:** AWS EC2 `t4g.medium` — ARM64 Graviton, 2 vCPU / 4 GiB, Ubuntu
- **EC2 host:** `ec2-13-206-58-237.ap-south-1.compute.amazonaws.com` (user `ubuntu`)
- **SSH from Windows:**
  ```powershell
  ssh -i "C:\Users\SWISS TECH\Documents\SSHfianacee_pk\financee_pk_key.pem" ubuntu@ec2-13-206-58-237.ap-south-1.compute.amazonaws.com
  ```
- **Repo:** `https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production`
- **Image:** `ghcr.io/maaz-bin-haider/financee-web`

> If you stop/start the instance without an Elastic IP, the public DNS/IP
> changes — update the `EC2_HOST` GitHub secret (Part C) when that happens.
> Consider allocating an **Elastic IP** in the EC2 console so it never changes.

---

## Part A — Prepare the EC2 instance (one time)

### A1. Instance and firewall (AWS console)

1. Size: production runs on a **`t4g.medium`** (ARM64 Graviton, 2 vCPU /
   4 GiB) from an Ubuntu **64-bit (Arm)** AMI; Postgres 16, Redis, Gunicorn and
   Nginx all run on this box. `deploy/docker-compose.yml` is tuned for 4 GiB
   (`shared_buffers=768MB`, `max_connections=120`, Gunicorn 4 workers × 4
   threads). The image is multi-arch, so an x86 instance of the same size works
   too. On a smaller box, set lower `WEB_CONCURRENCY` / `GUNICORN_THREADS` in
   `deploy/.env` and add swap (A4). Give the root EBS volume room for a few
   images: deploys refuse to start with less than 1 GiB free (Part E).
2. EC2 console → your instance → **Security** tab → security group →
   **Edit inbound rules**. You need:
   - **SSH (22)** — from `0.0.0.0/0` (GitHub Actions runners have changing
     IPs; access is protected by your key). Tighten later if you wish.
   - **HTTP (80)** — from `0.0.0.0/0` (the app).
   - **HTTPS (443)** — add it now too; needed once you set up TLS.
3. Do **not** open 5432/6379 — Postgres/Redis stay internal to Docker.

### A2. Connect from Windows

Open PowerShell:

```powershell
ssh -i "C:\Users\SWISS TECH\Documents\SSHfianacee_pk\financee_pk_key.pem" ubuntu@ec2-13-206-58-237.ap-south-1.compute.amazonaws.com
```

All commands below run **on the server** unless marked otherwise.

### A3. Install Docker Engine + Compose plugin

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# run docker without sudo (log out & back in after this)
sudo usermod -aG docker ubuntu
exit
```

Reconnect (same `ssh` command), then verify:

```bash
docker --version && docker compose version
```

### A4. (Optional) add swap on smaller instances

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Part B — First deployment (one time)

### B1. Clone the repo

```bash
cd ~
git clone https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production.git
cd Financee_Multitenant_Production/deploy
```

The default app dir is now `/home/ubuntu/Financee_Multitenant_Production` —
exactly what the CI deploy job assumes (so the `EC2_APP_DIR` secret is not
needed).

### B2. Create the production `.env`

```bash
cp .env.example .env
nano .env
```

Fill it in like this (replace the placeholders):

```env
# Generate on the server with:
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY=<paste-the-generated-value>

DEBUG=False

# IMPORTANT: 'localhost' must stay in this list — the deploy health check and
# the container healthcheck call the app as http://localhost/.
ALLOWED_HOSTS=localhost,ec2-13-206-58-237.ap-south-1.compute.amazonaws.com,13.206.58.237

# http:// for now; change to https://your.domain.com once TLS is set up.
CSRF_TRUSTED_ORIGINS=http://ec2-13-206-58-237.ap-south-1.compute.amazonaws.com

# REQUIRED while serving plain http:// on a real domain: otherwise cookies are
# marked Secure, the browser drops them over HTTP, and every login fails with
# "CSRF verification failed". REMOVE this line once HTTPS is live (Part F).
SECURE_COOKIES=False

DB_NAME=financee
DB_USER=financee
DB_PASSWORD=<a-long-random-password>
DB_HOST=db
DB_PORT=5432
```

Save (Ctrl+O, Enter) and exit (Ctrl+X). This file never leaves the server and
is never committed.

### B3. Build and start the stack

```bash
docker compose -f docker-compose.yml up -d --build
```

(`-f docker-compose.yml` matters: it ignores the local-dev override file.)
First run takes a few minutes. It builds the image and boots Postgres, which
runs `build_multitenant_db.sql` once on the empty volume: the Django/auth
tables plus the example `tenant_company_1` business schema. The web entrypoint
then applies the public migrations, registers that schema as the **Company
One** tenant (`register_bootstrap_tenant`, first boot only), applies
`production_hardening.sql` (which also lifts the seeded schema to version 6)
and `tenant_indexes.sql`, and starts Gunicorn.

Verify:

```bash
docker compose -f docker-compose.yml ps          # all 4 services Up, web (healthy)
docker compose -f docker-compose.yml logs --tail=30 web
curl -I http://localhost/authentication/login/   # expect HTTP/1.1 200 OK
```

Then from your Windows browser: `http://ec2-13-206-58-237.ap-south-1.compute.amazonaws.com/`
→ you should see the Financee login page.

### B4. Create the admin (superuser)

```bash
docker compose -f docker-compose.yml exec web python manage.py createsuperuser
```

Log in at `http://<your-ec2-dns>/admin/` with it.

### B5. Create your real company + users

In the admin panel:

1. **Companies & Subscriptions → Add** — creating a company automatically
   provisions its isolated tenant schema. Pick its **base currency** and **tax
   environment** now: both lock once the company has financial activity. (You
   can also rename/reuse the seeded "Company One".)
2. **Users → Add** — create each client user.
3. **Memberships → Add** — attach each user to their company (one company per
   user), and assign permissions/groups.
4. Optional: set each company's **Contact email**, subscription **Paid until**
   and **feature switches** (a new company starts with the default plan:
   Sales Reports, Draft Invoices, Opening Stock/Cash, Owner Equity, Month-End
   Close, CSV export and attachments are off until you tick them), and
   configure **Billing & email settings** (SMTP app password + test-email
   button).

---

## Part C — CI/CD configuration (one time, on GitHub)

All under `https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/settings`.

### C1. Repository secrets

Settings → **Secrets and variables → Actions** → *Secrets* tab →
**New repository secret**, one per row (the first three are required):

| Name | Value |
|---|---|
| `EC2_HOST` | `ec2-13-206-58-237.ap-south-1.compute.amazonaws.com` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | The **full contents** of `C:\Users\SWISS TECH\Documents\SSHfianacee_pk\financee_pk_key.pem` — open it in Notepad, Select All, copy, paste, including the `-----BEGIN RSA PRIVATE KEY-----` / `-----END RSA PRIVATE KEY-----` lines |
| `EC2_APP_DIR` | *Optional.* Only if you cloned somewhere other than `/home/ubuntu/Financee_Multitenant_Production` (B1) |
| `BACKUP_DEST` | *Only with `PHASE30_BACKUP_MODE=encrypted` (C4).* Absolute path on the server of an off-server (mounted or synced) directory for the pre-deploy backup |
| `BACKUP_PASSPHRASE_FILE` | *Only with encrypted mode.* Path on the server of the root-readable passphrase file for that backup |

### C2. The approval gates

Every release from `main` stops twice for a person:

1. **`staging-release-approval`** — after all test gates pass, before the image
   is published to GHCR.
2. **`production`** — before the deploy job touches the server.

For **each** of the two names: Settings → **Environments** → **New
environment** → name it exactly as above → **Configure environment** → tick
**Required reviewers** → add your own GitHub account → **Save protection
rules**.

Create both before the first release. GitHub creates a missing environment on
first use with **no** protection rules, and that job then runs without
waiting for anyone.

### C3. GHCR image access for the server

The deploy pulls `ghcr.io/maaz-bin-haider/financee-web` on the EC2 host.
Pick ONE:

- **Option A — make the package public (simplest).**
  `https://github.com/Maaz-Bin-Haider?tab=packages` → **financee-web** →
  **Package settings** → Danger Zone → **Change visibility → Public**.
  (The image contains the app code — which is already public with the repo —
  but no secrets; `.env` is never baked into the image.)

- **Option B — keep it private, log the server in once.**
  1. GitHub avatar → **Settings → Developer settings → Personal access
     tokens → Tokens (classic) → Generate new token** — tick only
     **`read:packages`**, generate, copy it.
  2. On the EC2 server:
     ```bash
     docker login ghcr.io -u Maaz-Bin-Haider
     # paste the token as the password (stored permanently)
     ```

### C4. Activate deploys

Settings → **Secrets and variables → Actions** → *Variables* tab →
**New repository variable**:

| Name | Value |
|---|---|
| `DEPLOY_ENABLED` | `true` |

Do this **last** — while it is unset, pushes to `main` still run every gate
and (after the staging approval) publish the image, but skip the deploy job
entirely.

Optional variables — the deploy job fills in a default when one is unset:

| Name | Default when unset | Purpose |
|---|---|---|
| `PHASE30_BACKUP_MODE` | `external` | `encrypted` makes every deploy take and verify an encrypted database + media backup first (needs the `BACKUP_*` secrets). `external` records that backups are handled separately (Part G) |
| `MAINTENANCE_NOTICE_REFERENCE` | `github-production-approval-<run id>` | Customer/operator notice recorded with the release |
| `MAINTENANCE_WINDOW_UTC` | `approved-production-run-<run id>` | Approved maintenance window recorded with the release |
| `ROLLBACK_OWNER` | the GitHub user who triggered the run | Operator accountable for a rollback |

### C5. First automated deploy (verify the pipeline)

1. Push a commit to `main` (or Actions tab → latest **CI/CD** run →
   **Re-run all jobs**). A commit whose message contains `[skip ci]` starts no
   run at all; the repo uses that for docs-only changes.
2. Watch the run: `checks` and the stack gates (serial, creation-freeze,
   runtime-removal, metadata-inventory, compatibility, cleanup-rehearsal,
   isolation, arm64-smoke, full-regression, recovery) run in parallel, then
   `staging-security-gate`.
3. **Product, engineering & operations staging approval** shows *Waiting for
   review* → **Review deployments** → tick `staging-release-approval` →
   **Approve and deploy**. `publish` then builds the multi-arch image and
   pushes `:<sha>` and `:latest` to GHCR.
4. **Deploy to EC2 (manual approval)** shows *Waiting for review* → approve
   `production` the same way.
5. The job SSHes to the server, runs `git pull --ff-only` in the checkout, and
   starts `deploy/phase30_foundation_deploy.sh`
   (`PHASE30_PRODUCTION_FOUNDATION_RUNBOOK.md`), which:
   - refuses to run unless the checkout is exactly the release commit and the
     image is pinned to that SHA;
   - runs `release_preflight` and, using the new image with its entrypoint
     disabled, records a read-only continuity fingerprint of every tenant;
   - takes the encrypted backup when `PHASE30_BACKUP_MODE=encrypted`;
   - calls `deploy_pull.sh`, which frees unused images, requires ≥ 1 GiB free
     disk, pulls the SHA-tagged image, recreates `web` (+ `nginx` when its
     config changed), health-checks `http://localhost/authentication/login/`
     through nginx, then re-applies `tenant_indexes.sql` and re-runs
     `release_preflight` (the new container's entrypoint has already applied
     migrations and `production_hardening.sql`);
   - checks that the continuity fingerprint is unchanged (balances, journals,
     serial state), then requires container health, three straight 200s
     through nginx, and the thresholds: login ≤ 5 s, ≤ 100 database
     connections, ≥ 1 GiB free disk, zero 5xx, container CPU and memory
     ≤ 90 %;
   - **rolls `web` back to the previous image automatically if any step after
     the deploy starts fails**, and writes `rollback-incident.txt`.

   Evidence for every run lands in `deploy/phase30-evidence/<release-sha>/` on
   the server. Nginx re-resolves `web` through Docker DNS on every request
   (`deploy/nginx/financee_common.conf`), so recreating `web` causes no 502s.

> **Approve promptly.** The controller insists that the server checkout equals
> the release commit, so a deploy approved after something else lands on
> `main` stops at that check without changing anything. Deploy the newest
> commit instead: merge the next change, or push a commit without `[skip ci]`
> to start a fresh run.

---

## Part D — Day-to-day workflow after setup

1. Commit and push to `main` (or merge a PR).
2. CI builds the image and runs every gate on disposable from-scratch stacks
   (fresh seeded database, extra tenants). Red run = nothing publishable,
   production untouched.
3. A green run pauses twice — staging approval, then production — and the
   Phase 30 controller ships it (C5).
4. Nothing else to do on the server. The old `deploy/deploy.sh`
   (build-on-server) remains as a manual fallback, but it has no preflight, no
   real health check (a fixed 5-second wait) and no rollback, so prefer
   re-running the CI deploy:
   ```bash
   cd ~/Financee_Multitenant_Production/deploy && ./deploy.sh
   ```

**Caveat to remember:** a rollback swaps the web *image* back, but it does
**not** revert public migrations, tenant SQL (the new container's entrypoint
applies `production_hardening.sql` before the health check), nginx, or the
server checkout — keep migrations and tenant patches backward-compatible (the
existing idempotent-patch discipline).

### Encrypted database and media recovery

Production recovery covers PostgreSQL and the media volume as one encrypted,
checksummed bundle. With `PHASE30_BACKUP_MODE=encrypted` (C4) every deploy
takes one first; otherwise run it yourself before risky changes. It is
separate from the daily database-only backup (Part G). The destination must be
off the EC2 instance and the passphrase must be stored separately:

```bash
cd ~/Financee_Multitenant_Production/deploy
BACKUP_DEST=/mnt/offsite/financee \
BACKUP_PASSPHRASE_FILE=/run/secrets/financee_backup_passphrase \
bash backup_encrypted.sh
```

Do not test a restore against the `deploy` production project. Use
`restore_rehearsal.sh`, an isolated `phase28_*` project, and non-production
credentials exactly as documented in `PHASE28_RECOVERY_RUNBOOK.md`. A backup
is not verified until its relocated sidecar passes and the isolated restore
reaches health, media verification, and all-tenant `release_preflight`.

---

## Part E — Troubleshooting on the server

### Deployment fails with `no space left on device`

The registry uses commit-SHA image tags. Those images are not "dangling", so
plain `docker image prune -f` does not remove superseded releases. On a small
EC2 root disk they can accumulate until containerd cannot extract a new ARM64
image.

`deploy_pull.sh` removes all images not referenced by a container and clears
unused build cache before its pull. It never prunes volumes, and Docker keeps
the image used by the currently running web container for rollback. The Phase
30 controller, though, pulls the candidate once earlier (for its read-only
audit), before that cleanup, so a nearly full disk can still fail there. To
recover:

```bash
cd ~/Financee_Multitenant_Production/deploy
docker system df
docker image prune -af
docker builder prune -af
df -h
# then re-run the failed "Deploy to EC2" job in GitHub Actions
```

If less than 1 GiB remains after cleanup, expand the instance's root EBS volume
before retrying. Do not run `docker volume prune`: PostgreSQL and uploaded media
use Docker volumes.

```bash
cd ~/Financee_Multitenant_Production/deploy

docker compose -f docker-compose.yml ps                  # is everything Up/healthy?
docker compose -f docker-compose.yml logs --tail=100 web   # Django/Gunicorn logs
docker compose -f docker-compose.yml logs --tail=50 nginx  # proxy logs
docker compose -f docker-compose.yml logs -f web nginx     # follow live
```

- **"CSRF verification failed. Request aborted." on every login/form** → the
  site is being served over plain `http://` while cookies are marked Secure
  (the `DEBUG=False` default), so the browser never sends them. Add
  `SECURE_COOKIES=False` to `deploy/.env`, then
  `docker compose -f docker-compose.yml up -d --force-recreate --no-deps web`.
  Remove the line again once HTTPS is live. Also confirm the exact scheme+host
  you browse with is listed in `CSRF_TRUSTED_ORIGINS`.
- **502 Bad Gateway** → check nginx logs. `connect() failed ... upstream` on a
  stack *without* the resolver fix means restart nginx:
  `docker compose -f docker-compose.yml restart nginx`. With the current
  config this should no longer happen.
- **Login redirect loop / 403 after login** → see `FIXED_ISSUES.md` (tenant
  schema version).
  `docker compose -f docker-compose.yml exec -T web python manage.py release_preflight`
  shows which tenant fails and why; re-apply hardening with:
  `docker compose -f docker-compose.yml exec -T web python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql`
- **Deploy job failed in GitHub** → open the job log (a failed `deploy_pull.sh`
  health check prints the last 100 web log lines), then the evidence on the
  server in `deploy/phase30-evidence/<release-sha>/`: preflight, continuity,
  deploy, monitoring and container logs, plus `rollback-incident.txt` when it
  rolled back. `Checked-out source does not match PHASE30_RELEASE_SHA` means
  `main` moved on before approval (C5).

---

## Part F — Custom domain + HTTPS (Cloudflare)

This section is written for **this** setup: the domain **`financee-swisstech.com`**
is on **Cloudflare** with both records **Proxied** (orange cloud):

| Name | Type | Content | Proxy |
|---|---|---|---|
| `financee-swisstech.com` | A | `13.206.58.237` (Elastic IP) | Proxied |
| `www.financee-swisstech.com` | CNAME | `financee-swisstech.com` | Proxied |

Because the domain is **proxied**, traffic is **Browser → Cloudflare → origin
(EC2)**. Cloudflare terminates TLS at its edge, so Let's Encrypt / certbot on
the origin is the wrong tool (the HTTP-01 challenge hits Cloudflare, not your
box). The correct, simplest path is a **Cloudflare Origin Certificate** on nginx
with SSL mode **Full (strict)** — a free cert valid up to 15 years, so there is
**no certbot and no renewal cron**, and encryption is end-to-end.

### How the repo is wired for this

- `deploy/nginx/financee.conf` — HTTP server on **port 80** (stays up for the
  localhost health checks; Cloudflare does the visitor HTTP→HTTPS redirect).
- `deploy/nginx/financee_tls.conf` — HTTPS server on **port 443** using the
  origin cert.
- `deploy/nginx/financee_common.conf` — the shared proxy/static/media body
  included by **both**, so they never drift.
- `deploy/docker-compose.tls.yml` — overlay that publishes 443 and mounts the
  cert. `phase30_foundation_deploy.sh`, `deploy_pull.sh` and `deploy.sh` add
  it **automatically once `/etc/nginx/cloudflare/origin.pem` exists on the
  host** — so nothing here breaks HTTP-only deploys before the cert is
  installed.

> **Ordering rule:** install the origin cert on the host **before** the first
> TLS-enabled deploy. The deploy scripts only switch nginx to 443 after they see
> `origin.pem`, so this is safe by construction — but do the Cloudflare + cert
> steps (F1–F2) before relying on HTTPS.

### F1. Cloudflare dashboard

1. **SSL/TLS → Overview → set encryption mode to `Full (strict)`.**
   (Not "Flexible" — that leaves Cloudflare→origin unencrypted and causes
   redirect loops. Not "Full" — that skips origin cert validation.)
2. **SSL/TLS → Origin Server → Create Certificate.** Accept defaults (RSA,
   hostnames `financee-swisstech.com, *.financee-swisstech.com`, 15 years).
   Cloudflare shows two blocks **once** — copy both now:
   - the **Origin Certificate** (`-----BEGIN CERTIFICATE-----` …)
   - the **Private Key** (`-----BEGIN PRIVATE KEY-----` …)
3. **SSL/TLS → Edge Certificates → turn on `Always Use HTTPS`** (Cloudflare
   redirects visitors to HTTPS at the edge). Optionally enable **HSTS** there
   too, but the origin already sends an HSTS header, so this is redundant.
4. Keep **SSL/TLS → Edge Certificates → Minimum TLS Version** at 1.2.

### F2. Install the origin cert on the EC2 host

On the server:

```bash
sudo mkdir -p /etc/nginx/cloudflare
sudo nano /etc/nginx/cloudflare/origin.pem   # paste the Origin Certificate block, save
sudo nano /etc/nginx/cloudflare/origin.key   # paste the Private Key block, save
sudo chmod 600 /etc/nginx/cloudflare/origin.key
sudo chmod 644 /etc/nginx/cloudflare/origin.pem
ls -l /etc/nginx/cloudflare/                  # both files present
```

These files live **only on the server** (never committed). The path
`/etc/nginx/cloudflare` is what `docker-compose.tls.yml` mounts into nginx.

### F3. Update the production `.env`

Edit `~/Financee_Multitenant_Production/deploy/.env`:

```env
ALLOWED_HOSTS=localhost,financee-swisstech.com,www.financee-swisstech.com,ec2-13-206-58-237.ap-south-1.compute.amazonaws.com,13.206.58.237
CSRF_TRUSTED_ORIGINS=https://financee-swisstech.com,https://www.financee-swisstech.com
```

- Keep `localhost` in `ALLOWED_HOSTS` (health checks call `http://localhost/`).
- **Remove the `SECURE_COOKIES=False` line** (delete it entirely). With HTTPS
  live, cookies must be `Secure` again — which they now can be, because
  Cloudflare→origin is HTTPS and nginx forwards `X-Forwarded-Proto: https`.
- Leave `SECURE_SSL_REDIRECT` unset. Cloudflare already forces HTTPS at the
  edge; enabling it in Django would only add a redirect on the localhost health
  path with no benefit.

### F4. Roll it out (get the repo changes onto the server, then recreate)

The nginx/compose files above ship via git. Get them onto the server and bring
nginx up on 443. Either:

- **Via CI (normal path):** merge to `main` and approve both gates. The deploy
  job git-pulls the checkout; the controller and `deploy_pull.sh` see
  `origin.pem`, add the TLS overlay, and recreate nginx on 443. Because you
  changed `.env` (not baked into the image), web must be recreated too so the
  new cookie/host settings load — the deploy recreates web anyway.

- **Manually on the server (immediate):**
  ```bash
  cd ~/Financee_Multitenant_Production/deploy
  git pull --ff-only

  # Validate the TLS config with the real cert mount BEFORE swapping nginx live
  # (CI never exercises the 443 block, so test it here). Expect "test is successful".
  docker compose -f docker-compose.yml -f docker-compose.tls.yml run --rm --no-deps nginx nginx -t

  docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --force-recreate nginx web
  docker compose -f docker-compose.yml logs --tail=30 nginx   # no ssl errors, listening on 443
  ```

### F5. Verify

```bash
# On the server — origin answers TLS with the Cloudflare origin cert:
curl -kIsS https://localhost/authentication/login/ | head -1     # HTTP/2 200
docker compose -f docker-compose.yml ps                          # nginx Up, web (healthy)
```

From your browser:

- `https://financee-swisstech.com/` → padlock, Financee login page.
- `http://financee-swisstech.com/` → redirects to `https://` (Cloudflare edge).
- Log in and submit a form → **no "CSRF verification failed"** (the pre-TLS
  cause is gone now that cookies are Secure over real HTTPS).

If a form still fails CSRF, confirm the exact scheme+host you browsed is in
`CSRF_TRUSTED_ORIGINS`, and that `SECURE_COOKIES=False` was actually removed
from `.env` and web was recreated.

### F6. (Recommended) Lock the origin to Cloudflare

While proxied, only Cloudflare should be able to reach ports 80/443 — otherwise
someone hitting the Elastic IP directly bypasses Cloudflare and can spoof
`X-Forwarded-For` (which the rate limiter trusts). In the EC2 **security group**,
replace the `0.0.0.0/0` rules on **80** and **443** with Cloudflare's published
IP ranges (`https://www.cloudflare.com/ips/`). Leave SSH (22) as is. Do this
only after HTTPS is confirmed working, so you don't lock yourself out of
debugging over the direct DNS name.

### F7. Cert renewal

Nothing to do — a Cloudflare Origin Certificate is valid up to 15 years. Set a
calendar reminder ~1 month before expiry to regenerate it (repeat F1.2 + F2 +
recreate nginx). Cloudflare's *edge* certificate (what visitors see) is
auto-managed and renews itself.

---

## Part G — Daily database backup (one time)

Separately from deploys, a systemd timer on the server takes an encrypted
PostgreSQL backup — the `public` schema plus every tenant schema, **but no
uploaded media** — and uploads it as a GitHub Release to the private repository
`Maaz-Bin-Haider/financee_pk_backup`. The full procedure (credentials, the
attended first run, the restore rehearsal, token rotation) is in
**`DATABASE_BACKUP_GITHUB_RUNBOOK.md`**. In short:

1. Put a fine-grained token scoped to that one repository in
   `/etc/financee-backup/github.env` and a strong passphrase in
   `/etc/financee-backup/passphrase`, both root-only (`0600`). Keep an offline
   copy of the passphrase: without it no backup can be restored.
2. Install `gh` and `jq`, run one attended backup with
   `run_database_backup.sh`, and pass an isolated restore rehearsal before
   relying on the timer.
3. Install and start the timer:
   ```bash
   cd ~/Financee_Multitenant_Production/deploy
   sudo FINANCEE_APP_DIR=/home/ubuntu/Financee_Multitenant_Production \
     bash install_database_backup_timer.sh
   sudo systemctl start financee-db-backup.timer
   systemctl list-timers financee-db-backup.timer
   ```
   It runs daily at 02:15 UTC (with up to 15 minutes of random delay) and
   catches up after downtime. Retention keeps the newest 30 daily releases
   plus the first one in each of the newest 12 months.
4. Check on it:
   ```bash
   sudo /home/ubuntu/Financee_Multitenant_Production/deploy/database_backup_status.sh
   ```
   It prints `STALE` and exits 1 when the newest backup is more than 26 hours
   old. Nothing runs this check on a schedule, so look at it regularly or hook
   it into your monitoring.

For a full recovery point that includes uploaded invoices, use the encrypted
database-and-media bundle in Part D.
