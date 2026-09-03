#!/usr/bin/env python3
"""Static, database-free contracts for the Phase 1 creation freeze."""

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
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
suite = read("tests/suite/run_all.py")
recovery = read("tests/phase28_recovery_rehearsal.sh")

choices_block = models.split("INVENTORY_MODE_CHOICES = (", 1)[1].split(")", 1)[0]
admin_exclude = admin.split("exclude = (", 1)[1].split(")", 1)[0]
admin_list = admin.split("list_display = (", 1)[1].split(")", 1)[0]
admin_filters = admin.split("list_filter = (", 1)[1].split(")", 1)[0]
full_modules = suite.split("MODULES = [", 1)[1].split("]", 1)[0]

checks = {
    "model choices expose serial only":
        "INVENTORY_MODE_SERIAL" in choices_block
        and "INVENTORY_MODE_QUANTITY" not in choices_block,
    "model validation rejects every non-serial value":
        "self.inventory_mode != INVENTORY_MODE_SERIAL" in models
        and "Only serial-number based companies are supported" in models,
    "physical serial constraint retained independently of ORM state":
        'condition=models.Q(inventory_mode="serial")' in migration
        and "migrations.SeparateDatabaseAndState" in compatibility
        and "expected validated serial-only constraint required" in compatibility
        and "DROP CONSTRAINT" not in compatibility,
    "admin excludes inventory mode from its form":
        '"inventory_mode"' in admin_exclude,
    "admin removes inventory mode column and filter":
        '"inventory_mode"' not in admin_list
        and '"inventory_mode"' not in admin_filters,
    "CLI has no inventory-mode option and assigns serial":
        '"--inventory-mode"' not in command
        and "inventory_mode=INVENTORY_MODE_SERIAL" in command,
    "low-level and company provisioning reject non-serial":
        provisioning.count("only serial") >= 2
        and "family != INVENTORY_MODE_SERIAL" in provisioning
        and "company.inventory_mode != INVENTORY_MODE_SERIAL" in provisioning,
    "retry provisioning rejects non-serial first":
        "company.inventory_mode != INVENTORY_MODE_SERIAL" in retry
        and retry.index("company.inventory_mode != INVENTORY_MODE_SERIAL")
        < retry.index("company.provisioning_state not in"),
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
