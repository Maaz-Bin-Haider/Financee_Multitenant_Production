#!/usr/bin/env python3
"""Database-free contracts for the Phase 4 entry gate and transition plan."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


audit = read("tenancy/management/commands/serial_only_phase4_audit.py")
wrapper = read("deploy/phase4_inventory_remote.sh")
workflow = read(".github/workflows/phase4-migration-leaf-inspection.yml")
plan = read("SERIAL_ONLY_REMOVAL_PLAN.md")
postgres_fixture = read("tests/phase3b_cleanup.py")
audit_tree = ast.parse(audit)
audit_sql = []
for node in ast.walk(audit_tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        continue
    if node.func.attr != "execute" or not node.args:
        continue
    value = node.args[0]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        audit_sql.append(value.value)
    elif isinstance(value, ast.JoinedStr):
        audit_sql.append("".join(
            part.value for part in value.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ))

checks = {
    "audit forces repeatable read-only transaction": (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in audit
        and "SET TRANSACTION READ ONLY" in audit
    ),
    "audit SQL contains no write or DDL statement": (
        bool(audit_sql)
        and all(statement.lstrip().upper().startswith(("SELECT", "SET"))
                for statement in audit_sql)
    ),
    "exact pre-squash migration leaves are required": (
        '"0009_inventory_mode_compatibility"' in audit
        and '"0025_add_quantity_platform_permissions"' in audit
        and "tuple(observed[\"tenancy\"]) == TENANCY_MIGRATIONS" in audit
        and "tuple(observed[\"authentication\"]) == AUTHENTICATION_MIGRATIONS" in audit
    ),
    "post-cleanup column permissions and features must be absent": (
        "retired inventory_mode column is present" in audit
        and "retired quantity permissions remain" in audit
        and "retired feature keys remain" in audit
    ),
    "reversal archive must remain applied and checksummed": (
        "Phase 3B reversal archive is absent" in audit
        and "archive_rows[0][2] == \"applied\"" in audit
        and 're.fullmatch(r"[0-9a-f]{64}"' in audit
        and "ARCHIVE_MARKER" in audit
    ),
    "only canonical active ready serial schemas pass": (
        "company registry is not canonical active ready serial-only" in audit
        and "tenant schema registry drift exists" in audit
        and "retired quantity-family schema detected" in audit
        and "strpos(nspname, 'tenant_company_') = 1" in audit
        and "to_regclass(quote_ident(%s)" in audit
    ),
    "audit output explicitly authorizes nothing": (
        '"authorizes_migration_replacement": False' in audit
        and "PHASE4_REPLACEMENT_AUTHORIZED=no" in wrapper
    ),
    "remote transport pins exact healthy ARM64 image": (
        "expected_deployed_sha" in wrapper
        and "deployed image mismatch" in wrapper
        and "web is not healthy" in wrapper
        and "image is not ARM64" in wrapper
    ),
    "remote database sessions are independently forced read-only": (
        wrapper.count("PGOPTIONS=-c default_transaction_read_only=on") == 2
        and "serial_only_phase0_audit --include-continuity" in wrapper
    ),
    "container and image are unchanged after inspection": (
        "web container changed during inspection" in wrapper
        and "web image changed during inspection" in wrapper
        and "PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes" in wrapper
    ),
    "workflow is manual protected and serialized with deployments": (
        "workflow_dispatch:" in workflow
        and "environment: production" in workflow
        and "group: production-deploy" in workflow
        and "contents: read" in workflow
    ),
    "workflow transports only read-only audit source": (
        "INSPECT-PHASE4-MIGRATION-LEAVES" in workflow
        and "serial_only_phase4_audit.py" in workflow
        and "phase4_inventory_remote.sh" in workflow
        and "--action apply" not in workflow
    ),
    "two-release Django migration transition is mandatory": (
        "Checkpoint 4A" in plan
        and "Checkpoint 4B" in plan
        and "old migration files remain" in plan
        and "remove `replaces`" in plan
    ),
    "real PostgreSQL cleanup fixture executes the Phase 4 audit": (
        "phase4_audit.inspect()" in postgres_fixture
        and "Phase 4 entry audit accepts exact post-cleanup migration and serial state"
        in postgres_fixture
    ),
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
raise SystemExit(0 if all(checks.values()) else 1)
