#!/usr/bin/env bash
# Prove production helper restores supported workers, stops unsupported workers
# on rollback, and fails a candidate whose heartbeat/image health is wrong.
set -euo pipefail
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
cat >"$scratch/docker" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "WEB_IMAGE=${WEB_IMAGE:-} $*" >>"$WORKER_TEST_LOG"
case "$*" in
  *"run --rm --network none --entrypoint python old-image "*) exit 1;;
  *"ps -q report_worker") echo worker;;
  *"ps -q web") echo web;;
  "inspect -f {{.Image}} "*) echo sha256:matching;;
  "inspect -f {{.State.Health.Status}} "*) echo "${WORKER_TEST_HEALTH:-healthy}";;
esac
FAKE
chmod +x "$scratch/docker"
export PATH="$scratch:$PATH" WORKER_TEST_LOG="$scratch/docker.log"
WEB_IMAGE=new-image bash deploy/report_worker_control.sh start
rg -q 'up -d --no-deps --wait --wait-timeout 150 report_worker' "$WORKER_TEST_LOG"
: >"$WORKER_TEST_LOG"
WEB_IMAGE=old-image bash deploy/report_worker_control.sh restore
rg -q 'stop report_worker' "$WORKER_TEST_LOG"
if rg -q 'up -d' "$WORKER_TEST_LOG"; then exit 1; fi
if WEB_IMAGE=new-image WORKER_TEST_HEALTH=unhealthy bash deploy/report_worker_control.sh start; then exit 1; fi
printf '%s\n' 'PASS: matching worker start, old-image rollback stop, and unhealthy-worker rejection'
