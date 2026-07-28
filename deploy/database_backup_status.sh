#!/usr/bin/env bash
set -euo pipefail

readonly APPROVED_REPOSITORY="Maaz-Bin-Haider/financee_pk_backup"
env_file="${GITHUB_BACKUP_ENV_FILE:-/etc/financee-backup/github.env}"
state_file="${BACKUP_STATE_FILE:-/var/lib/financee-backup/last-success.env}"

[[ -r "$env_file" ]] || {
    echo "Backup environment file is not readable: $env_file" >&2
    exit 2
}
# shellcheck disable=SC1090
source "$env_file"
: "${GITHUB_BACKUP_REPOSITORY:?Missing GITHUB_BACKUP_REPOSITORY}"
: "${GH_TOKEN:?Missing GH_TOKEN}"
[[ "$GITHUB_BACKUP_REPOSITORY" == "$APPROVED_REPOSITORY" ]] || {
    echo "Refusing unapproved GitHub repository" >&2
    exit 2
}

echo "SERVICE_ACTIVE=$(systemctl is-active financee-db-backup.service 2>/dev/null || true)"
echo "TIMER_ACTIVE=$(systemctl is-active financee-db-backup.timer 2>/dev/null || true)"
echo "TIMER_ENABLED=$(systemctl is-enabled financee-db-backup.timer 2>/dev/null || true)"
systemctl list-timers financee-db-backup.timer --no-pager || true

if [[ -r "$state_file" ]]; then
    # Values written by run_database_backup.sh contain only controlled
    # timestamps, release tags, sizes, and basenames.
    # shellcheck disable=SC1090
    source "$state_file"
    echo "LOCAL_LAST_SUCCESS_UTC=${LAST_SUCCESS_UTC:-unknown}"
    echo "LOCAL_LAST_RELEASE=${LAST_RELEASE:-unknown}"
    echo "LOCAL_LAST_BACKUP_BYTES=${LAST_BACKUP_BYTES:-unknown}"
fi

remote_json=$(gh api "repos/$GITHUB_BACKUP_REPOSITORY/releases?per_page=100")
latest=$(
    jq -r '
      [.[] | select(.draft == false)
       | select(.tag_name | test("^db-backup-[0-9]{8}T[0-9]{6}Z$"))]
      | sort_by(.tag_name) | last | .tag_name // empty
    ' <<<"$remote_json"
)
[[ -n "$latest" ]] || {
    echo "REMOTE_BACKUP_STATUS=STALE"
    echo "REMOTE_BACKUP_REASON=no-managed-release"
    exit 1
}

set +e
freshness=$(
    python3 - "$latest" <<'PY'
import datetime
import re
import sys

match = re.fullmatch(r"db-backup-(\d{8}T\d{6}Z)", sys.argv[1])
if not match:
    raise SystemExit(2)
created = datetime.datetime.strptime(
    match.group(1), "%Y%m%dT%H%M%SZ"
).replace(tzinfo=datetime.timezone.utc)
age = int((datetime.datetime.now(datetime.timezone.utc) - created).total_seconds())
print(f"REMOTE_BACKUP_AGE_SECONDS={age}")
print("REMOTE_BACKUP_STATUS=FRESH" if age <= 26 * 3600 else "REMOTE_BACKUP_STATUS=STALE")
raise SystemExit(0 if age <= 26 * 3600 else 1)
PY
)
status=$?
set -e
echo "REMOTE_LAST_RELEASE=$latest"
echo "$freshness"
exit "$status"
