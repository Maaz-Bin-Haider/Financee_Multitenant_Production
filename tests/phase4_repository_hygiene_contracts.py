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
compat = read("tests/serial_api_compat.py")
recovery_local = read("tests/phase3_recovery_local.py")
suite_runner = read("tests/suite/run_all.py")
ci = read(".github/workflows/ci.yml")
project_context = read("PROJECT_CONTEXT.md")
readme = read("README.md")
claude_md = read("CLAUDE.md")
migration_proof = read("tests/phase4a_migration_proof.sh")
bootstrap_sql = read("build_multitenant_db.sql")
entrypoint_sh = read("deploy/entrypoint.sh")
bootstrap_command = read(
    "tenancy/management/commands/register_bootstrap_tenant.py")

RETIRED_PATHS = (
    "deploy/retire_quantity_static.py",
    "tests/test_phase2_static_retirement.py",
    "tests/phase26_performance_capacity.py",
    "ARCHITECTURE_QUANTITY_COMPANY.md",
    "SRS_QUANTITY_BASED_COMPANY.md",
    "IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md",
    "REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md",
)
PRESERVED_PATHS = (
    "tenancy/management/commands/serial_only_phase3_cleanup.py",
    "tenancy/management/commands/serial_only_phase3_audit.py",
    "PHASE3B_MAINTENANCE_RUNBOOK.md",
    ".github/workflows/phase3b-controlled-cleanup.yml",
    "tenancy/migrations/0005_company_inventory_mode.py",
    "tenancy/migrations/0008_serial_only_company_creation.py",
    "tenancy/migrations/0009_inventory_mode_compatibility.py",
    "tenancy/sql/tenant_template.sql",
    "tenancy/sql/production_hardening.sql",
    "tests/phase3a_old_image.py",
    "tests/phase26_capacity_preflight.py",
)
# Modules the Phase 3 recovery gate runs inside the *previously published*
# image; each must tolerate both application shapes.
DUAL_IMAGE_MODULES = (
    "tests/suite/test_company_metadata.py",
    "tests/phase1_serial_only_creation.py",
    "tests/phase2_serial_runtime_removal.py",
    "tests/phase24_serial_matrix.py",
    "tests/phase25_four_company_isolation.py",
)
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
    "4A: every retired quantity-family artifact is gone": (
        all(not (ROOT / path).exists() for path in RETIRED_PATHS)
        and not any((ROOT / "tenancy/sql").glob("quantity_*.sql"))
        and not any((ROOT / "tests/suite").glob("test_quantity_*.py"))
        and not any((ROOT / "tests").glob("PHASE*QUANTITY*_RESULTS.md"))
    ),
    "4A: the reversal path and migration history are preserved": (
        all((ROOT / path).exists() for path in PRESERVED_PATHS)
    ),
    "4A: no source or test references a deleted module or symbol": (
        "retire_quantity_static" not in read("deploy/entrypoint.sh")
        and "test_phase2_static_retirement" not in ci
        and "test_quantity_" not in suite_runner
        and "phase26_performance_capacity" not in ci
    ),
    "4A: dual-image modules use the version-adaptive compatibility shim": (
        all("serial_api_compat" in read(path) for path in DUAL_IMAGE_MODULES)
        and "tests/suite/run_all.py" in recovery_local
        and "RETIRED_API_PRESENT" in compat
        and "Delete this module in checkpoint 4B" in compat
    ),
    "4A: the shim covers both rejection shapes without weakening either": (
        "except TypeError:" in compat
        and "except ValidationError:" in compat
        and "return False" in compat
    ),
    "4A: active documentation describes the serial-only system": (
        "Retired Quantity-Company Family" in project_context
        and "Phase 4 (repository hygiene)" in project_context
        and "Do not reintroduce an inventory-mode concept" in claude_md
        and "There is no inventory-mode concept left to configure" in readme
    ),
    "4A: documentation still warns that serial line quantities are not the family": (
        'ordinary word "quantity" is not by itself' in project_context
        and 'ordinary word "quantity" is *not* evidence' in claude_md
    ),
    "4A: the migration-replacement proof exists and is a mandatory CI gate": (
        (ROOT / "tests/phase4a_migration_proof.sh").exists()
        and "migration-replacement-gate:" in ci
        and "tests/phase4a_migration_proof.sh" in ci
    ),
    "4A: the proof covers both required migration paths fail-closed": (
        "never creates the retired inventory_mode column" in migration_proof
        and "never creates the 14 retired quantity permissions" in migration_proof
        and "applies no migration to that database" in migration_proof
        and "the replaced rows remain for the checkpoint 4B prune" in migration_proof
        and 'exit "$FAILED"' in migration_proof
    ),
    "4A: the bootstrap no longer defeats the tenancy squash": (
        "CREATE TABLE IF NOT EXISTS public.tenancy_company" not in bootstrap_sql
        and "'tenancy', '0001_initial'" not in bootstrap_sql
        and "register_bootstrap_tenant" in entrypoint_sh
        and "Company.objects.exists()" in bootstrap_command
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
