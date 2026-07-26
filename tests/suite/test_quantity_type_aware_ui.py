#!/usr/bin/env python3
"""Phase 21 central dispatch, payload-family, UI, and accessibility contracts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.test import RequestFactory  # noqa: E402

from tenancy.capabilities import (  # noqa: E402
    CAPABILITY_CATALOG, dispatch_inventory_view, parse_quantity_payload,
    reject_quantity_payload, reject_serial_payload,
)
from tenancy.models import INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL  # noqa: E402

RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def request(mode, payload=None):
    factory = RequestFactory()
    req = factory.post("/", data=json.dumps(payload or {}),
                       content_type="application/json")
    req.user = SimpleNamespace(pk=41)
    req.tenant_company = SimpleNamespace(inventory_mode=mode)
    return req


def checks():
    chk("central catalogue separates serial and quantity capabilities",
        "serial_lookup" in CAPABILITY_CATALOG[INVENTORY_MODE_SERIAL]
        and "serial_lookup" not in CAPABILITY_CATALOG[INVENTORY_MODE_QUANTITY]
        and "fifo" in CAPABILITY_CATALOG[INVENTORY_MODE_QUANTITY])
    serial = lambda _request: "serial"
    quantity = lambda _request: "quantity"
    chk("trusted serial dispatch", dispatch_inventory_view(
        request(INVENTORY_MODE_SERIAL), serial, quantity) == "serial")
    chk("trusted quantity dispatch", dispatch_inventory_view(
        request(INVENTORY_MODE_QUANTITY), serial, quantity) == "quantity")
    parsed = parse_quantity_payload(
        request(INVENTORY_MODE_QUANTITY, {"items": [{"quantity": "1"}]})
    )
    chk("quantity parser stamps trusted actor", parsed["created_by_id"] == 41)
    try:
        reject_serial_payload({"items": [{"serial_number": "X"}]})
        blocked = False
    except ValueError:
        blocked = True
    chk("quantity parser rejects nested serial fields", blocked)
    try:
        reject_quantity_payload({"items": [{"variant_id": 1}]})
        blocked = False
    except ValueError:
        blocked = True
    chk("serial parser rejects nested quantity identifiers", blocked)
    response = dispatch_inventory_view(
        request(INVENTORY_MODE_SERIAL, {"items": [{"warehouse_id": 2}]}),
        serial, quantity,
    )
    chk("serial dispatch independently blocks quantity bypass",
        response.status_code == 400)

    templates = [
        "quantity_purchasing_template.html", "quantity_sale_template.html",
        "quantity_sale_return_template.html",
        "quantity_purchase_return_template.html", "quantity_transfers.html",
        "quantity_counts.html", "quantity_warehouses.html",
    ]
    template_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.joinpath("templates").rglob("*.html")
        if path.name in templates
    )
    workflow_js = ROOT.joinpath("static/js/quantity_workflow.js").read_text(
        encoding="utf-8")
    workflow_css = ROOT.joinpath("static/css/quantity_workflow.css").read_text(
        encoding="utf-8")
    chk("all quantity workflows load shared interaction layer",
        template_text.count("quantity_workflow.js") == len(templates))
    chk("duplicate submit and loading state implemented",
        "quantityBusy" in workflow_js and 'aria-busy' in workflow_js)
    chk("keyboard save workflow implemented",
        "ctrlKey" in workflow_js and 'key === \"Enter\"' in workflow_js)
    chk("mobile and reduced-motion rules implemented",
        "@media (max-width: 768px)" in workflow_css
        and "prefers-reduced-motion" in workflow_css)
    chk("warehouse form provides accessible live status",
        'role="status"' in template_text and 'aria-live="polite"' in template_text)
    chk("authoritative calculation controls rendered",
        template_text.count('id="preview"') == 2)
    chk("quantity attachment condition uses real feature context",
        "financee_features" not in template_text)


def main():
    checks()
    failed = [result for result in RESULTS if not result[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              "" if ok or not detail else f"— {detail}")
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 21 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
