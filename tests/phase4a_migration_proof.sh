#!/usr/bin/env bash
# Checkpoint 4A migration-replacement proof (disposable Compose projects only).
#
# Proves the two properties the serial-only plan requires before a 4A release:
#   1. a fresh database uses only the squashed serial state and never creates
#      the retired inventory_mode column, its constraint, or the retired
#      quantity permissions;
#   2. a database still on the original leaves produces a no-op migration plan
#      and retains its data.
#
# Property 1 originally failed: build_multitenant_db.sql seeded
# ('tenancy','0001_initial'), which left the tenancy replacement permanently
# *partially* applied. Django only uses a replacement when ALL or NONE of the
# migrations it replaces are applied, so it discarded the replacement, replayed
# the original chain, and 0005 recreated the retired column. The bootstrap no
# longer creates the tenancy registry or seeds that row; `migrate` owns the
# public tenancy schema and the entrypoint calls `register_bootstrap_tenant`.
#
# Requires: the published 3A image and a locally built current image.
# Creates and removes only freshly named disposable projects.
set -uo pipefail
cd "$(dirname "$0")/../deploy" || exit 2
OLD_IMAGE=${PHASE4A_OLD_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:497b6650ed678bc462f85de6bff14692bffd6ace}
NEW_IMAGE=${PHASE4A_NEW_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:latest}
FAILED=0

check() { # check "<name>" "<actual>" "<expected>"
  if [ "$2" = "$3" ]; then printf 'PASS: %s\n' "$1"
  else printf 'FAIL: %s (got %s, want %s)\n' "$1" "$2" "$3"; FAILED=1; fi
}

mkproj() {
  proj="p4a_$1_$(date +%s)_$$"; work=$(mktemp -d); env_file="$work/e.env"
  cat > "$env_file" <<ENV
SECRET_KEY=proof-only-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee_proof
DB_USER=financee_proof
DB_PASSWORD=proof-password
DB_HOST=db
DB_PORT=5432
ENV
  export WEB_ENV_FILE="$env_file"
}
psql() { docker compose --project-name "$proj" --env-file "$env_file" -f docker-compose.yml exec -T db psql -U financee_proof -d financee_proof -Atc "$1"; }
dc() { docker compose --project-name "$proj" --env-file "$env_file" -f docker-compose.yml "$@"; }
teardown() { dc down -v >/dev/null 2>&1; rm -rf "$work"; }

echo "== Part 1: fresh install through the real bootstrap =="
mkproj fresh
trap teardown EXIT
if ! WEB_IMAGE="$NEW_IMAGE" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1; then
  echo "FAIL: fresh stack did not start"; WEB_IMAGE="$NEW_IMAGE" dc logs web | tail -20; teardown; exit 1
fi
check "fresh install records the squashed tenancy replacement" \
  "$(psql "SELECT count(*) FROM public.django_migrations WHERE app='tenancy' AND name='0001_serial_only'")" 1
check "fresh install records the squashed authentication replacement" \
  "$(psql "SELECT count(*) FROM public.django_migrations WHERE app='authentication' AND name='0001_serial_only'")" 1
check "fresh install never creates the retired inventory_mode column" \
  "$(psql "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode'")" 0
check "fresh install never creates the retired serial-only constraint" \
  "$(psql "SELECT count(*) FROM pg_constraint WHERE conname='tenancy_company_valid_inventory_mode'")" 0
check "fresh install never creates the 14 retired quantity permissions" \
  "$(psql "SELECT count(*) FROM public.auth_permission p JOIN public.django_content_type ct ON ct.id=p.content_type_id WHERE ct.app_label='auth' AND ct.model='user' AND p.codename IN ('view_warehouse','create_warehouse','update_warehouse','delete_warehouse','view_warehouse_transfer','create_warehouse_transfer','update_warehouse_transfer','delete_warehouse_transfer','view_physical_count','create_physical_count','approve_inventory_adjustment','reverse_inventory_adjustment','view_quantity_audit','manage_quantity_attachments')")" 0
check "the bootstrap example tenant is registered exactly once" \
  "$(psql "SELECT count(*) FROM public.tenancy_company WHERE schema_name='tenant_company_1'")" 1
check "the registered bootstrap tenant is active and ready" \
  "$(psql "SELECT count(*) FROM public.tenancy_company WHERE schema_name='tenant_company_1' AND is_active AND provisioning_state='ready'")" 1
check "fresh install has nothing left to migrate" \
  "$(WEB_IMAGE="$NEW_IMAGE" dc exec -T web python manage.py migrate --plan 2>/dev/null | grep -c 'No planned migration operations.')" 1
check "re-running the registration is a no-op" \
  "$(WEB_IMAGE="$NEW_IMAGE" dc exec -T web python manage.py register_bootstrap_tenant 2>/dev/null | grep -c 'registry already populated')" 1
teardown; trap - EXIT

echo
echo "== Part 2: database at the original leaves, upgraded to 4A =="
mkproj upgrade
trap teardown EXIT
if ! WEB_IMAGE="$OLD_IMAGE" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1; then
  echo "FAIL: published 3A stack did not start"; WEB_IMAGE="$OLD_IMAGE" dc logs web | tail -20; teardown; exit 1
fi
check "published 3A image reaches the exact pre-squash tenancy leaf" \
  "$(psql "SELECT count(*) FROM public.django_migrations WHERE app='tenancy' AND name='0009_inventory_mode_compatibility'")" 1
WEB_IMAGE="$OLD_IMAGE" dc exec -T web python manage.py provision_tenant "Proof Serial Co" >/dev/null 2>&1
before_companies=$(psql "SELECT count(*) FROM public.tenancy_company")
before_digest=$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM public.tenancy_company t")
before_perms=$(psql "SELECT count(*) FROM public.auth_permission")
check "the 4A image plans no migration operations on that database" \
  "$(WEB_IMAGE="$NEW_IMAGE" dc run --rm --no-deps --entrypoint python web manage.py migrate --plan 2>/dev/null | grep -c 'No planned migration operations.')" 1
check "the 4A image applies no migration to that database" \
  "$(WEB_IMAGE="$NEW_IMAGE" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input 2>/dev/null | grep -c 'No migrations to apply.')" 1
check "company rows are retained" "$(psql "SELECT count(*) FROM public.tenancy_company")" "$before_companies"
check "the company registry is byte-identical after the upgrade" \
  "$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM public.tenancy_company t")" "$before_digest"
check "permissions are retained" "$(psql "SELECT count(*) FROM public.auth_permission")" "$before_perms"
check "the replacement is now recorded" \
  "$(psql "SELECT count(*) FROM public.django_migrations WHERE app='tenancy' AND name='0001_serial_only'")" 1
check "the replaced rows remain for the checkpoint 4B prune" \
  "$(psql "SELECT count(*) FROM public.django_migrations WHERE app='tenancy' AND name LIKE '000%' AND name<>'0001_serial_only'")" 9
teardown; trap - EXIT

echo
if [ "$FAILED" -eq 0 ]; then echo "PHASE4A_MIGRATION_PROOF=PASS"; else echo "PHASE4A_MIGRATION_PROOF=FAIL"; fi
exit "$FAILED"
