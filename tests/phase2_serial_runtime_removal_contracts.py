#!/usr/bin/env python3
"""Database-free contracts for the Phase 2 quantity-runtime removal."""

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


RUNTIME_FILES = (
    "items/quantity_views.py",
    "purchase/quantity_views.py",
    "sale/quantity_views.py",
    "purchaseReturn/quantity_views.py",
    "saleReturn/quantity_views.py",
    "tenancy/audit_urls.py",
    "tenancy/audit_views.py",
    "tenancy/count_urls.py",
    "tenancy/count_views.py",
    "tenancy/quantity_tax.py",
    "tenancy/report_catalog.py",
    "tenancy/report_urls.py",
    "tenancy/report_views.py",
    "tenancy/transfer_urls.py",
    "tenancy/transfer_views.py",
    "tenancy/warehouse_urls.py",
    "tenancy/warehouse_views.py",
)

UI_FILES = (
    "templates/opening_stock_templates/quantity_opening_stock_template.html",
    "templates/purchase_return_templates/quantity_purchase_return_template.html",
    "templates/purchase_templates/quantity_purchasing_template.html",
    "templates/reports/quantity_reports.html",
    "templates/sale_return_templates/quantity_sale_return_template.html",
    "templates/sale_templates/quantity_sale_template.html",
    "templates/tenancy_templates/quantity_audit.html",
    "templates/tenancy_templates/quantity_counts.html",
    "templates/tenancy_templates/quantity_transfers.html",
    "templates/tenancy_templates/quantity_warehouses.html",
    "static/css/quantity_reports.css",
    "static/css/quantity_workflow.css",
    "static/js/quantity_counts.js",
    "static/js/quantity_opening_stock.js",
    "static/js/quantity_purchase_returns.js",
    "static/js/quantity_purchases.js",
    "static/js/quantity_reports.js",
    "static/js/quantity_sale_returns.js",
    "static/js/quantity_sales.js",
    "static/js/quantity_transfers.js",
    "static/js/quantity_warehouses.js",
    "static/js/quantity_workflow.js",
)

urls = "\n".join(read(path) for path in (
    "financee/urls.py", "items/urls.py", "purchase/urls.py",
    "purchaseReturn/urls.py", "saleReturn/urls.py",
))
business_views = "\n".join(read(path) for path in (
    "purchase/views.py", "sale/views.py", "purchaseReturn/views.py",
    "saleReturn/views.py", "opening_stock/views.py", "home/views.py",
))
capabilities = read("tenancy/capabilities.py")
middleware = read("tenancy/middleware.py")
families = read("tenancy/schema_families.py")
rollout = read("tenancy/management/commands/apply_sql_all_tenants.py")
preflight = read("tenancy/management/commands/release_preflight.py")
entrypoint = read("deploy/entrypoint.sh")
features = read("tenancy/features.py")
security = read("financee/security.py")
attachments = read("attachments/utils.py")
base = read("templates/base/base.html")
workflow = read(".github/workflows/ci.yml")
stack = read("tests/ci_phase27_stack.sh")
suite = read("tests/suite/run_all.py")

quantity_family_block = families.split(
    "INVENTORY_MODE_QUANTITY: SchemaFamily(", 1
)[1].split("),\n    }", 1)[0]

# Extracted from deployed Phase 1 commit 102e55e857bbffa8bd4318e6afaec42e048c8e67.
# These are independent regression anchors, not hashes of the candidate itself.
SERIAL_FUNCTION_BASELINES = {
    "purchase/views.py": "97eb75b61f469da18156a3c20fd3184b42f87a57c0951482ead214b38881cefb",
    "sale/views.py": "c385a60296ef81904dfc6d99d68f6b317a209fd45aa1d5b37fd764c24b6d91d4",
    "purchaseReturn/views.py": "8355ff92824990af9c6a19a571d916886227a8886e91112d2db9e0cdd01b5875",
    "saleReturn/views.py": "06e7cd03c2be1c88cb6bbb83cef1b795e914e3ebc1cad5a098a9b414ae1cb080",
}


def function_hash(path):
    source = read(path)
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name.startswith("_serial_")]
    # Hash exact source, not ast.dump(), whose formatting varies by Python version.
    return hashlib.sha256("\n".join(
        ast.get_source_segment(source, node) for node in functions
    ).encode()).hexdigest()


def files_hash(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode() + b"\0" + (ROOT / path).read_bytes() + b"\0")
    return digest.hexdigest()


serial_ui_paths = [path.relative_to(ROOT).as_posix()
                   for directory in ("static", "templates")
                   for path in (ROOT / directory).rglob("*")
                   if path.is_file() and not path.name.startswith((".", "quantity_"))
                   and path.relative_to(ROOT).as_posix() != "templates/base/base.html"]
serial_sql_paths = [path.relative_to(ROOT).as_posix()
                    for path in (ROOT / "tenancy/sql").glob("*.sql")
                    if not path.name.startswith("quantity_")] + ["build_multitenant_db.sql"]

checks = {
    "12 serial document implementations are source-identical to deployed Phase 1":
        all(function_hash(path) == expected for path, expected in SERIAL_FUNCTION_BASELINES.items()),
    "212 serial UI source files are byte-identical to deployed Phase 1":
        len(serial_ui_paths) == 212
        and files_hash(serial_ui_paths) == "cae8e5e425906e5b8b26deb33a8a15b8dc73ef0a665473b55d307c0faf648bb6",
    "17 serial SQL/bootstrap files are byte-identical to deployed Phase 1":
        len(serial_sql_paths) == 17
        and files_hash(serial_sql_paths) == "15a1171224a3a3d06e5b77dfb76c518f27555812d01922e698ca4e98b0c166af",
    "quantity HTTP adapter and route modules are absent":
        all(not (ROOT / path).exists() for path in RUNTIME_FILES),
    "quantity templates and static assets are absent":
        all(not (ROOT / path).exists() for path in UI_FILES),
    "root and app URL configurations expose no quantity routes":
        "quantity" not in urls
        and "warehouse_urls" not in urls
        and "transfer_urls" not in urls
        and "count_urls" not in urls,
    "business views import no quantity adapter or dispatcher":
        "quantity_views" not in business_views
        and "dispatch_inventory_view" not in business_views,
    "business views execute no quantity SQL or templates":
        "quantity_" not in business_views,
    "serial document wrappers retain the trusted request boundary":
        business_views.count("return serial_inventory_view") == 12
        and "reject_non_serial_payload(payload)" in capabilities,
    "capability module contains no quantity runtime catalogue or parser":
        "INVENTORY_MODE_QUANTITY" not in capabilities
        and "parse_quantity_payload" not in capabilities
        and "reject_serial_payload" not in capabilities,
    "quantity schema descriptor remains runtime disabled with no path exceptions":
        "runtime_enabled=False" in quantity_family_block
        and "enabled_path_prefixes=()" in quantity_family_block,
    "middleware still fails closed through schema runtime status":
        "definition.runtime_enabled or path_enabled" in middleware,
    "tenant SQL rollout command accepts serial only":
        "choices=[INVENTORY_MODE_SERIAL]" in rollout
        and "Only serial tenant SQL rollout is supported" in rollout
        and "INVENTORY_MODE_QUANTITY" not in rollout,
    "container startup performs serial SQL maintenance only":
        "--family serial" in entrypoint
        and "--family quantity" not in entrypoint
        and "quantity_reports_dashboards.sql" not in entrypoint
        and "quantity_platform_controls.sql" not in entrypoint,
    "release preflight accepts and probes serial only":
        'choices=("serial",)' in preflight
        and "company.inventory_mode != INVENTORY_MODE_SERIAL" in preflight
        and "quantity_run_report" not in preflight
        and "SELECT get_trial_balance_json()" in preflight,
    "serial feature registry exposes no retired controls":
        "quantity_controls" not in features
        and "purchase_reports" not in features,
    "security path map contains no retired route permissions":
        "/quantity-reports/" not in security
        and "/warehouses/quantity/" not in security
        and "/physical-counts/" not in security,
    "serial attachment lookup contains no schema-family fallback":
        "QUANTITY_DOCUMENT_CONFIG" not in attachments
        and "manage_quantity_attachments" not in attachments,
    "shared base template has no quantity branch or link":
        "is_quantity_company" not in base
        and "quantity_" not in base
        and "Quantity Reports" not in base,
    "historical SQL and migrations remain for controlled Phase 3 cleanup":
        (ROOT / "tenancy/sql/quantity_tenant_template.sql").is_file()
        and (ROOT / "tenancy/migrations/0005_company_inventory_mode.py").is_file(),
    "mandatory Phase 2 local and CI gates are wired":
        "phase2_serial_runtime_removal_contracts.py" in workflow
        and "runtime-removal-gate:" in workflow
        and "phase2_serial_runtime_removal.py" in stack
        and "phase2_serial_runtime_removal.py" in suite,
    "test cleanup is confined to a uniquely named disposable Compose project":
        '--project-name "$test_project"' in stack
        and 'test_project="phase27_' in stack
        and 'cat > "$WEB_ENV_FILE"' in stack
        and "deploy/.env" not in stack,
    "retired generated static cleanup is narrow and explicitly tested":
        "python deploy/retire_quantity_static.py" in entrypoint
        and "test_phase2_static_retirement" in workflow,
    "protected exact-SHA production workflow remains intact":
        "environment: production" in workflow
        and "PHASE30_RELEASE_SHA='${{ github.sha }}'" in workflow,
}

failed = [name for name, passed in checks.items() if not passed]
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 2 contracts passed")
raise SystemExit(1 if failed else 0)
