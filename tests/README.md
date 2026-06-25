# Functional Test Suite

Two complementary harnesses that together exercise **every** business operation
and **every** report in the system.

| File | What it tests | How |
|---|---|---|
| `test_system.py` | All stored-function entry types (create/update/delete for sale, purchase, sale-return, purchase-return, payment, receipt, contra) + parties, items, opening stock, opening cash, owner equity, month close + **every** report function & view | Direct SQL per tenant schema (mirrors the middleware's `search_path`) |
| `test_http.py` | The real HTTP endpoints (permissions, view logic, JSON, templates) for reports, lists, dashboard, and the main write flows | Django test `Client` as a logged-in tenant user |

## Setup (one time)

Keep this `tests/` folder in your **project root** (next to `manage.py`). You do
**not** need to rebuild the image — the runner copies the tests into the running
web container for you. The runner also auto-detects your compose file whether it
sits in the project root or in `./deploy`.

## Run

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh            # copy tests into the container + run both harnesses
./tests/run_tests.sh --reset    # ALSO wipe + re-provision tenants first (clean signal)
```

If your compose file or web service has non-standard names, override them:

```bash
COMPOSE_FILE=deploy/docker-compose.yml WEB_SERVICE=web ./tests/run_tests.sh
```

Or run a harness manually (after the runner has copied the folder in once):

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/test_system.py
docker compose -f deploy/docker-compose.yml exec web python tests/test_http.py
```

> **`--reset` erases tenant data.** It drops and rebuilds every tenant schema
> from the template. Shared `public` data (users, the company list) is kept.
> Use it for a pristine `112/112` signal; omit it to test against current data.

## Reading the output

- `test_system.py` prints `N/M passed` per tenant and a de-duplicated list of
  distinct failure types. A clean run is `112/112 passed` on each tenant.
- `test_http.py` lists every endpoint with `[ok]` / `[FAIL]` and the response
  body for any problem.

## Re-running on the same database

The harness creates fresh master records each run (names carry a time tag), so
repeated runs don't collide on parties/items. **But** two operations are
single-shot by design and may report a conflict on a second run against the same
data: **opening cash** (a singleton row) and **month close** (one close per
period). For a perfectly clean signal, use `--reset`, which drops and
re-provisions the tenant schemas from the template before running.
