#!/usr/bin/env python3
"""Static, database-free contracts for the Phase 1 creation freeze.

Phase 1 froze company creation to serial by *rejecting* every non-serial
value. Checkpoint 4A removed the retired family outright, so the freeze is now
enforced by absence: no supported code path can even express a non-serial
company. These contracts therefore assert the stronger invariant while keeping
the retired physical constraint history intact.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


models = read("tenancy/models.py")
admin = read("tenancy/admin.py")
provisioning = read("tenancy/provisioning.py")
command = read("tenancy/management/commands/provision_tenant.py")
retry = read("tenancy/management/commands/retry_tenant_provisioning.py")
migration = read("tenancy/migrations/0008_serial_only_company_creation.py")
compatibility = read("tenancy/migrations/0009_inventory_mode_compatibility.py")
squashed = read("tenancy/migrations/0001_serial_only.py")
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
suite = read("tests/suite/run_all.py")
recovery = read("tests/phase28_recovery_rehearsal.sh")

admin_list = admin.split("list_display = (", 1)[1].split(")", 1)[0]
admin_filters = admin.split("list_filter = (", 1)[1].split(")", 1)[0]
full_modules = suite.split("MODULES = [", 1)[1].split("]", 1)[0]

checks = {
    "model exposes no inventory-mode concept at all":
        "INVENTORY_MODE" not in models
        and "inventory_mode" not in models
        and "CompanyQuerySet" not in models,
    "model cannot express a non-serial company":
        "quantity" not in models.lower()
        and "def clean(self):" in models,
    "physical serial constraint retained independently of ORM state":
        'condition=models.Q(inventory_mode="serial")' in migration
        and "migrations.SeparateDatabaseAndState" in compatibility
        and "expected validated serial-only constraint required" in compatibility
        and "DROP CONSTRAINT" not in compatibility,
    "squashed replacement replaces the exact retired creation history":
        "('tenancy', '0008_serial_only_company_creation')" in squashed
        and "('tenancy', '0009_inventory_mode_compatibility')" in squashed
        and "replaces = [" in squashed,
    "squashed replacement never recreates the retired column":
        "inventory_mode" not in squashed.split("operations = [", 1)[1]
        and "quantity" not in squashed.split("operations = [", 1)[1].lower(),
    "admin exposes no inventory mode anywhere":
        "inventory_mode" not in admin
        and '"inventory_mode"' not in admin_list
        and '"inventory_mode"' not in admin_filters,
    "CLI has no inventory-mode option and no mode argument":
        '"--inventory-mode"' not in command
        and "inventory_mode" not in command,
    "provisioning accepts the serial family only":
        "only serial tenant provisioning is supported" in provisioning
        and "family != SERIAL_SCHEMA_FAMILY" in provisioning
        and "inventory_mode" not in provisioning,
    "retry provisioning carries no retired mode branch":
        "inventory_mode" not in retry
        and "company.provisioning_state not in" in retry,
    "migration inspects registry before replacing constraint":
        "Company.objects.exclude(inventory_mode=\"serial\")" in migration
        and migration.index("migrations.RunPython(require_serial_registry")
        < migration.index("migrations.RemoveConstraint"),
    "migration preserves the existing constraint name":
        migration.count("tenancy_company_valid_inventory_mode") == 2
        and "condition=models.Q(inventory_mode=\"serial\")" in migration,
    "mandatory creation-freeze gate replaces quantity gate":
        "creation-freeze-gate:" in workflow
        and "quantity-gate:" not in workflow
        and "tests/phase1_serial_only_creation.py" in stack,
    "mandatory ARM64 and four-serial isolation gates remain":
        "arm64-smoke:" in workflow
        and "Four-serial-company isolation gate" in workflow,
    "aggregate active suite runs no quantity modules":
        "test_quantity_" not in full_modules
        and "phase1_serial_only_creation.py" in full_modules,
    "recovery rehearsal creates no quantity company":
        "--inventory-mode quantity" not in recovery
        and "Phase 28 Forward Serial" in recovery,
    "protected production deployment remains intact":
        "environment: production" in workflow
        and "PHASE30_RELEASE_SHA='${{ github.sha }}'" in workflow,
}

failed = [name for name, passed in checks.items() if not passed]
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 1 contracts passed")
raise SystemExit(1 if failed else 0)
