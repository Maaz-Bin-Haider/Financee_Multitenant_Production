#!/usr/bin/env bash
set -euo pipefail

# Retire one explicitly approved, orphaned quantity test schema. This script is
# intentionally narrower than a general tenant-deletion utility: it refuses a
# registered company, a serial/mixed/unknown schema, or a target whose name does
# not deterministically match the company id.

cd "$(dirname "$0")"

action="${RETIRE_ACTION:-inspect}"
company_id="${RETIRE_COMPANY_ID:-}"
expected_schema="${RETIRE_EXPECTED_SCHEMA:-}"
confirmation="${RETIRE_CONFIRMATION:-}"
audit_image="${RETIRE_AUDIT_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:8f407dea9e488eab8980b48309c064a00db714cd}"

[[ "$action" == "inspect" || "$action" == "execute" ]] || {
    echo "RETIRE_ACTION must be inspect or execute" >&2
    exit 2
}
[[ "$company_id" =~ ^[1-9][0-9]*$ ]] || {
    echo "RETIRE_COMPANY_ID must be a positive integer" >&2
    exit 2
}
[[ "$expected_schema" =~ ^tenant_company_[1-9][0-9]*$ ]] || {
    echo "RETIRE_EXPECTED_SCHEMA is not an approved tenant identifier" >&2
    exit 2
}
[[ "$expected_schema" == "tenant_company_${company_id}" ]] || {
    echo "Company id and expected schema do not match" >&2
    exit 2
}

compose=(docker compose -f docker-compose.yml)
if [[ -f /etc/nginx/cloudflare/origin.pem && -f docker-compose.tls.yml ]]; then
    compose+=(-f docker-compose.tls.yml)
fi

psql_cmd=(
    "${compose[@]}" exec -T db psql -X -v ON_ERROR_STOP=1
    -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}"
)

scalar() {
    "${psql_cmd[@]}" -Atc "$1" | tr -d '\r'
}

company_row_count=$(scalar \
    "SELECT count(*) FROM public.tenancy_company WHERE id = ${company_id}")
schema_registry_count=$(scalar \
    "SELECT count(*) FROM public.tenancy_company WHERE schema_name = '${expected_schema}'")
schema_exists=$(scalar \
    "SELECT count(*) FROM pg_namespace WHERE nspname = '${expected_schema}'")
quantity_marker=$(scalar \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${expected_schema}' AND table_name = 'tenant_schema_metadata' AND table_type = 'BASE TABLE'")
serial_marker=$(scalar \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${expected_schema}' AND table_name = 'tenant_schema_version' AND table_type = 'BASE TABLE'")
table_count=$(scalar \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${expected_schema}' AND table_type = 'BASE TABLE'")
schema_bytes=$(scalar \
    "SELECT COALESCE(sum(pg_total_relation_size(c.oid)), 0) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = '${expected_schema}'")

family="missing"
if [[ "$schema_exists" == "1" && "$quantity_marker" == "1" && "$serial_marker" == "0" ]]; then
    family=$(scalar \
        "SELECT COALESCE((SELECT family FROM \"${expected_schema}\".tenant_schema_metadata WHERE id = true), 'missing-metadata-row')")
elif [[ "$schema_exists" == "1" && "$quantity_marker" == "1" && "$serial_marker" == "1" ]]; then
    family="mixed"
elif [[ "$schema_exists" == "1" && "$serial_marker" == "1" ]]; then
    family="serial"
elif [[ "$schema_exists" == "1" ]]; then
    family="unknown"
fi

echo "RETIRE_ACTION=${action}"
echo "RETIRE_COMPANY_ID=${company_id}"
echo "RETIRE_EXPECTED_SCHEMA=${expected_schema}"
echo "COMPANY_ROW_COUNT=${company_row_count}"
echo "SCHEMA_REGISTRY_REFERENCE_COUNT=${schema_registry_count}"
echo "PHYSICAL_SCHEMA_COUNT=${schema_exists}"
echo "SCHEMA_FAMILY=${family}"
echo "SCHEMA_TABLE_COUNT=${table_count}"
echo "SCHEMA_BYTES=${schema_bytes}"

if [[ "$action" == "inspect" ]]; then
    echo "==> Running the complete database-enforced read-only Phase 0 audit"
    WEB_IMAGE="$audit_image" "${compose[@]}" run --rm --no-deps -T \
        --entrypoint python web manage.py serial_only_phase0_audit \
        --include-continuity
    echo "RETIRE_RESULT=INSPECTION_ONLY"
    exit 0
fi

# The owner already removed Company 2 through Django admin. Execution is only
# permitted for the resulting orphan. A still-registered company requires a
# different, attended procedure so its public audit relationships are visible.
[[ "$company_row_count" == "0" ]] || {
    echo "Refusing: Company id ${company_id} is still registered" >&2
    exit 3
}
[[ "$schema_registry_count" == "0" ]] || {
    echo "Refusing: another registry row references ${expected_schema}" >&2
    exit 3
}
[[ "$schema_exists" == "1" ]] || {
    echo "Refusing: exact physical schema is not present" >&2
    exit 3
}
[[ "$quantity_marker" == "1" && "$serial_marker" == "0" && "$family" == "quantity" ]] || {
    echo "Refusing: target is not an unambiguous quantity-family schema" >&2
    exit 3
}
[[ "$confirmation" == "DROP-ORPHAN-TENANT-COMPANY-${company_id}" ]] || {
    echo "Refusing: exact retirement confirmation is missing" >&2
    exit 3
}
[[ "${RETIRE_BACKUP_DEST_CONFIRMED_OFFSERVER:-no}" == "yes" ]] || {
    echo "Refusing: off-server backup destination was not explicitly confirmed" >&2
    exit 3
}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence_dir="retirement-evidence/company-${company_id}-${stamp}"
mkdir -p "$evidence_dir"

echo "==> Capturing privacy-safe pre-change estate evidence"
WEB_IMAGE="$audit_image" "${compose[@]}" run --rm --no-deps -T \
    --entrypoint python web manage.py serial_only_phase0_audit \
    --include-continuity >"$evidence_dir/phase0-before.json"

echo "==> Creating and remotely verifying a fresh encrypted full-database backup"
backup_started_epoch=$(date -u +%s)
backup_reference=""
if [[ -n "${BACKUP_DEST:-}" || -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
    [[ "${BACKUP_DEST:-}" = /* ]] || {
        echo "Refusing: BACKUP_DEST must be absolute" >&2
        exit 3
    }
    [[ -s "${BACKUP_PASSPHRASE_FILE:-}" ]] || {
        echo "Refusing: backup passphrase file is unavailable" >&2
        exit 3
    }
    BACKUP_DEST="$BACKUP_DEST" \
    BACKUP_PASSPHRASE_FILE="$BACKUP_PASSPHRASE_FILE" \
        bash backup_database_encrypted.sh | tee "$evidence_dir/backup.txt"
    grep -qx 'BACKUP_RESULT=PASS' "$evidence_dir/backup.txt"
    backup_path=$(sed -n 's/^BACKUP_PATH=//p' "$evidence_dir/backup.txt" | tail -1)
    [[ -n "$backup_path" && -s "$backup_path" && -s "$backup_path.sha256" ]]
    backup_reference="$backup_path"
else
    # Production normally uses the root-owned systemd job. It encrypts the
    # complete database, uploads both assets to the allowlisted private backup
    # repository, downloads/verifies them independently, then records success.
    command -v sudo >/dev/null
    sudo -n true
    sudo -n systemctl cat financee-db-backup.service >/dev/null
    sudo -n systemctl start financee-db-backup.service
    sudo -n bash database_backup_status.sh | tee "$evidence_dir/backup.txt"
    grep -qx 'REMOTE_BACKUP_STATUS=FRESH' "$evidence_dir/backup.txt"
    backup_release=$(sed -n 's/^REMOTE_LAST_RELEASE=//p' "$evidence_dir/backup.txt" | tail -1)
    python3 - "$backup_release" "$backup_started_epoch" <<'PY'
import datetime
import re
import sys

match = re.fullmatch(r"db-backup-(\d{8}T\d{6}Z)", sys.argv[1])
if not match:
    raise SystemExit("Backup service did not report a managed release")
created = datetime.datetime.strptime(
    match.group(1), "%Y%m%dT%H%M%SZ"
).replace(tzinfo=datetime.timezone.utc)
if int(created.timestamp()) < int(sys.argv[2]):
    raise SystemExit("Backup release predates this retirement operation")
PY
    backup_reference="github-release:${backup_release}"
fi

echo "==> Dropping only the approved orphan schema in one PostgreSQL transaction"
"${psql_cmd[@]}" <<SQL
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';
SELECT pg_advisory_xact_lock(hashtextextended('financee-retire-orphan-test-tenant', 0));
DO \$retire\$
BEGIN
    IF EXISTS (SELECT 1 FROM public.tenancy_company WHERE id = ${company_id}) THEN
        RAISE EXCEPTION 'Company id was recreated; refusing retirement';
    END IF;
    IF EXISTS (SELECT 1 FROM public.tenancy_company WHERE schema_name = '${expected_schema}') THEN
        RAISE EXCEPTION 'Schema was re-registered; refusing retirement';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = '${expected_schema}'
           AND table_name = 'tenant_schema_metadata'
           AND table_type = 'BASE TABLE'
    ) OR EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema = '${expected_schema}'
           AND table_name = 'tenant_schema_version'
           AND table_type = 'BASE TABLE'
    ) THEN
        RAISE EXCEPTION 'Schema family changed; refusing retirement';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM "${expected_schema}".tenant_schema_metadata
         WHERE id = true AND family = 'quantity'
    ) THEN
        RAISE EXCEPTION 'Quantity metadata proof failed; refusing retirement';
    END IF;
END
\$retire\$;
DROP SCHEMA "${expected_schema}" CASCADE;
COMMIT;
SQL

echo "==> Proving the orphan is gone and all remaining tenants are serial and healthy"
[[ "$(scalar "SELECT count(*) FROM pg_namespace WHERE nspname = '${expected_schema}'")" == "0" ]]
[[ "$(scalar "SELECT count(*) FROM public.tenancy_company WHERE id = ${company_id} OR schema_name = '${expected_schema}'")" == "0" ]]
WEB_IMAGE="$audit_image" "${compose[@]}" run --rm --no-deps -T \
    --entrypoint python web manage.py serial_only_phase0_audit \
    --include-continuity --strict-serial >"$evidence_dir/phase0-after.json"
"${compose[@]}" exec -T web python manage.py release_preflight --require-family serial \
    >"$evidence_dir/release-preflight-after.txt"
curl -fsS --retry 5 --retry-delay 2 --retry-all-errors \
    -o /dev/null http://localhost/authentication/login/

echo "RETIRE_BACKUP_REFERENCE=${backup_reference}"
echo "RETIRE_EVIDENCE_DIR=${evidence_dir}"
echo "RETIRE_RESULT=PASS"
