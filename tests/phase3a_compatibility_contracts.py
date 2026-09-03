#!/usr/bin/env python3
"""Database-free preservation and release-wiring contracts for checkpoint 3A."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return (ROOT / path).read_text()

model = read("tenancy/models.py")
migration = read("tenancy/migrations/0009_inventory_mode_compatibility.py")
tree = ast.parse(migration)
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
live = read("tests/phase3a_compatibility.py")
old = read("tests/phase3a_old_image.py")
recovery = read("tests/phase28_recovery_rehearsal.sh")
company = next(n for n in ast.parse(model).body if isinstance(n, ast.ClassDef) and n.name == "Company")
concrete = {t.id for n in company.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
sql = [n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
       and isinstance(n.func, ast.Attribute) and n.func.attr == "execute" and n.args
       and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)]
query_dependencies = []
query_sources = [path for path in (ROOT / "tenancy").rglob("*.py") if "migrations" not in path.parts]
query_sources += [ROOT / path for path in (
    "tests/ci_bootstrap.py", "tests/test_http.py", "tests/suite/test_attachments.py",
    "tests/phase2_serial_runtime_removal.py",
)]
for path in query_sources:
    for node in ast.walk(ast.parse(path.read_text())):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"filter", "exclude", "update", "values", "values_list", "only", "defer", "order_by"}):
            names = [kw.arg for kw in node.keywords if kw.arg]
            names += [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
            if any(name.lstrip("-").split("__")[0] == "inventory_mode" for name in names):
                query_dependencies.append(f"{path.relative_to(ROOT)}:{node.lineno}")
checks = {
    "inventory mode is no longer a concrete Company field": "inventory_mode" not in concrete,
    "legacy display and explicit-input validation are preserved":
        "def get_inventory_mode_display(self)" in model and "self.inventory_mode != INVENTORY_MODE_SERIAL" in model,
    "bulk inserts also reject explicit non-serial legacy input":
        "def bulk_create(self, objs" in model and "if obj.inventory_mode != INVENTORY_MODE_SERIAL" in model,
    "shared currency tax and provisioning constraints remain":
        all(name in concrete for name in ("base_currency", "tax_environment", "provisioning_state", "disabled_features"))
        and "tenancy_company_valid_tax_environment" in model and "tenancy_company_valid_provisioning_state" in model,
    "state-only removal is paired with guarded reversible expansion":
        "migrations.SeparateDatabaseAndState" in migration
        and "database_operations=[migrations.RunPython(forwards, backwards)]" in migration
        and "state_operations=[" in migration and "migrations.RemoveField" in migration,
    "expansion executes no destructive SQL or data update":
        not any(any(token in statement.upper() for token in ("DROP COLUMN", "DROP CONSTRAINT", "DROP SCHEMA", "DELETE FROM", "UPDATE PUBLIC", "TRUNCATE")) for statement in sql),
    "migration preserves exact validated serial constraint":
        "pg_get_expr(conbin, conrelid)" in migration
        and 'constraint[:3] != ("c", True, False)' in migration
        and "inventory_mode::text='serial'::text" in migration,
    "migration blocks unexpected type nullability default and nonserial rows":
        'column != ("character varying(16)", True, expected_default)' in migration
        and "inventory_mode IS DISTINCT FROM 'serial'" in migration,
    "migration waits are bounded and table is locked during validation":
        "lock_timeout = '2s'" in migration and "statement_timeout = '30s'" in migration
        and "IN ACCESS EXCLUSIVE MODE" in migration and "atomic = True" in migration,
    "existing serial SQL rollout no longer filters an ORM legacy column":
        "inventory_mode=" not in read("tenancy/management/commands/apply_sql_all_tenants.py"),
    "runtime and active test discovery have no legacy ORM-column query": not query_dependencies,
    "continuity audit handles legacy-column presence and absence explicitly":
        "has_legacy_mode" in read("tenancy/management/commands/serial_only_phase0_audit.py")
        and "legacy_modes.get" in read("tenancy/management/commands/serial_only_phase0_audit.py"),
    "migration and absent-column tests are restricted to disposable stacks":
        'PHASE3A_TEST_DISPOSABLE' in live and 'PHASE3A_TEST_DISPOSABLE' in old
        and "transaction.set_rollback(True)" in live,
    "old deployed image actually creates and edits a company":
        "Company.objects.create" in old and "company.save(update_fields" in old
        and "e44737f1f740fa936e853a3d6bbbd068a1b6d89d" in stack,
    "new image checks application SQL with physical column removed":
        "DROP COLUMN inventory_mode" in live and "CaptureQueriesContext" in live
        and "queries.captured_queries" in live,
    "compatibility is mandatory for staging and publication":
        workflow.count("metadata-inventory-gate, compatibility-gate,") == 2,
    "ARM64 executes new compatibility tests":
        "phase3a_compatibility.py" in stack.split("  arm64)", 1)[1].split("  full)", 1)[0],
    "recovery rollback targets actual deployed Phase 2 and tests old-image creation":
        "e44737f1f740fa936e853a3d6bbbd068a1b6d89d" in recovery
        and "Phase 3A Old Image Serial" in recovery,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if query_dependencies:
    print("Legacy query dependencies: " + ", ".join(query_dependencies))
print(f"{sum(checks.values())}/{len(checks)} Phase 3A contracts passed")
raise SystemExit(0 if all(checks.values()) else 1)
