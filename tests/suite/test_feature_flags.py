#!/usr/bin/env python3
"""Per-company feature flags: registry/model semantics, admin form round-trip,
middleware URL enforcement (group + sub-report blocking, GET redirects vs JSON
denials), UI hiding (sidebar links, report buttons, CSV buttons, attachment
widget), and the attachment upload guard.

Everything mutates only the public-schema ``Company.disabled_features`` column
(plus a temporary superuser membership, mirroring suite/test_http.py) and
restores it in ``finally`` — no tenant business data is touched.

Run inside the web container:
    docker compose -f deploy/docker-compose.yml exec -e PYTHONPATH=/app web \
        python tests/suite/test_feature_flags.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402

from attachments.utils import validate_request_attachments  # noqa: E402
from tenancy.admin import CompanyAdminForm, _feature_field_name  # noqa: E402
from tenancy.features import (  # noqa: E402
    FEATURE_GROUPS,
    FEATURE_PATH_PREFIXES,
    all_feature_keys,
    feature_for_path,
    features_map,
)
from tenancy.models import Company, Membership  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))
    return bool(ok)


def make_client():
    server = "localhost"
    allowed = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*", "")]
    if allowed:
        server = allowed[0].lstrip(".")
    return Client(SERVER_NAME=server)


# ── Registry / model semantics (unsaved Company: no signals, no schema) ─────

def check_registry_and_model():
    keys = all_feature_keys()
    chk("registry has the 8 top-level groups",
        set(FEATURE_GROUPS) == {
            "accounts_reports", "stock_reports", "monthly_reports",
            "sales_reports", "opening_stock", "opening_cash",
            "excel_export", "attachments",
        }, sorted(FEATURE_GROUPS))
    chk("every enforced path maps to a registered key",
        all(key in keys for _, key in FEATURE_PATH_PREFIXES),
        [key for _, key in FEATURE_PATH_PREFIXES if key not in keys])
    chk("longest prefixes win (ledger2 before ledger)",
        feature_for_path("/accountsReports/detailed-ledger2/") == "accounts_reports.detailed_ledger2"
        and feature_for_path("/accountsReports/detailed-ledger/") == "accounts_reports.detailed_ledger")
    chk("sales report API resolves to its sub-key",
        feature_for_path("/sales-reports/api/trend/") == "sales_reports.trend")
    chk("sales report page resolves to the group",
        feature_for_path("/sales-reports/") == "sales_reports")
    chk("unenforced path resolves to None", feature_for_path("/home/") is None)

    co = Company(name=f"feat_{TAG}")
    chk("default company: everything enabled",
        all(co.feature_enabled(k) for k in keys))

    co.disabled_features = ["stock_reports"]
    chk("disabled group disables the group", not co.feature_enabled("stock_reports"))
    chk("disabled group disables its subs",
        not co.feature_enabled("stock_reports.serial_ledger"))
    chk("disabled group leaves other groups alone",
        co.feature_enabled("accounts_reports.cash_ledger"))

    co.disabled_features = ["sales_reports.trend"]
    chk("disabled sub disables only that sub",
        not co.feature_enabled("sales_reports.trend")
        and co.feature_enabled("sales_reports")
        and co.feature_enabled("sales_reports.summary"))

    co.disabled_features = ["no_such_feature"]
    chk("unknown keys fail open", co.feature_enabled("accounts_reports"))

    co.disabled_features = ["excel_export", "monthly_reports.monthly_income"]
    fmap = features_map(co)
    chk("features_map reflects single-switch feature",
        fmap["excel_export"]["enabled"] is False)
    chk("features_map reflects sub switch",
        fmap["monthly_reports"]["enabled"] is True
        and fmap["monthly_reports"]["subs"]["monthly_income"] is False
        and fmap["monthly_reports"]["subs"]["monthly_position"] is True)
    chk("features_map with no company is all-enabled",
        features_map(None)["excel_export"]["enabled"] is True)


# ── Admin form round-trip ────────────────────────────────────────────────────

def check_admin_form(company):
    form = CompanyAdminForm(instance=company)
    chk("admin form exposes a switch per feature key",
        all(_feature_field_name(k) in form.fields for k in all_feature_keys()))
    chk("admin form initial mirrors enabled state",
        all(form.fields[_feature_field_name(k)].initial == company.feature_enabled(k)
            for k in all_feature_keys()))

    data = {
        "name": company.name,
        "inventory_mode": company.inventory_mode,
        "base_currency": company.base_currency_id,
        "tax_environment": company.tax_environment,
        "contact_email": company.contact_email or "",
        "paid_until": company.paid_until or "",
        "grace_days": company.grace_days,
        "warn_days_before": company.warn_days_before,
        "is_active": company.is_active,
        "is_suspended": company.is_suspended,
    }
    for key in all_feature_keys():
        data[_feature_field_name(key)] = True
    data[_feature_field_name("excel_export")] = False
    data[_feature_field_name("stock_reports.item_detail")] = False

    form = CompanyAdminForm(data=data, instance=company)
    if not chk("admin form validates", form.is_valid(), form.errors.as_text()):
        return
    obj = form.save(commit=False)  # not persisted; instance-only
    chk("unticked switches land in disabled_features",
        set(obj.disabled_features) == {"excel_export", "stock_reports.item_detail"},
        obj.disabled_features)


# ── Admin change view (modelform_factory validates declared fields) ─────────

def check_admin_views(company):
    import re

    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    client = make_client()
    client.force_login(superuser)

    url = f"/admin/tenancy/company/{company.pk}/change/"
    resp = client.get(url)
    if not chk("admin change form renders", resp.status_code == 200, resp.status_code):
        return
    html = resp.content.decode("utf-8", "ignore")
    chk("admin change form shows feature fieldsets", "Features — " in html)
    chk("admin change form shows every switch",
        all(f'name="{_feature_field_name(k)}"' in html for k in all_feature_keys()))

    # Full POST round-trip through the real admin (inlines included).
    data = {
        "name": company.name,
        "base_currency": company.base_currency_id,
        "tax_environment": company.tax_environment,
        "contact_email": company.contact_email or "",
        "paid_until": company.paid_until.isoformat() if company.paid_until else "",
        "grace_days": company.grace_days,
        "warn_days_before": company.warn_days_before,
        "_save": "Save",
    }
    if company.is_active:
        data["is_active"] = "on"
    if company.is_suspended:
        data["is_suspended"] = "on"
    for prefix in set(re.findall(r'name="([^"]+)-TOTAL_FORMS"', html)):
        data[f"{prefix}-TOTAL_FORMS"] = "0"
        data[f"{prefix}-INITIAL_FORMS"] = "0"
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
    for key in all_feature_keys():
        data[_feature_field_name(key)] = "on"
    del data[_feature_field_name("excel_export")]
    del data[_feature_field_name("sales_reports.trend")]

    snapshot = list(company.disabled_features or [])
    try:
        resp = client.post(url, data)
        error_text = re.sub(r"<[^>]+>", " ", resp.content.decode("utf-8", "ignore"))
        error_text = " ".join(error_text.split())
        chk(
            "admin save redirects",
            resp.status_code == 302,
            f"{resp.status_code}: {error_text[:2000]}",
        )
        fresh = Company.objects.get(pk=company.pk)
        chk("admin save persists unticked switches",
            set(fresh.disabled_features) == {"excel_export", "sales_reports.trend"},
            fresh.disabled_features)
    finally:
        Company.objects.filter(pk=company.pk).update(disabled_features=snapshot)


# ── HTTP enforcement + UI hiding through the real middleware ────────────────

def set_features(company_pk, disabled):
    Company.objects.filter(pk=company_pk).update(disabled_features=list(disabled))


def check_http(company):
    client = make_client()
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    client.force_login(superuser)

    # Everything enabled: full UI, all pages reachable.
    set_features(company.pk, [])
    resp = client.get("/home/")
    html = resp.content.decode("utf-8", "ignore")
    chk("all-on: /home/ is 200", resp.status_code == 200, resp.status_code)
    chk("all-on: feature JSON embedded", 'id="financee-features"' in html)
    # Guards against double-encoding: window.FinanceeFeatures must be a JSON
    # OBJECT. If the map were pre-dumped to a string before json_script, the
    # quotes would be \"-escaped, this substring would vanish, and every JS
    # feature check would silently fail open (CSV buttons reappear).
    chk("all-on: feature JSON is an object, not a double-encoded string",
        '"excel_export": {"enabled": true' in html)
    # Multi-line {# #} comments are invalid in Django templates: the tail of
    # the comment renders as visible page text (has happened twice now).
    chk("all-on: no template-comment text leaks into the page", "#}" not in html)
    for label in ("Accounts Reports", "Stock Reports", "Monthly Reports",
                  "Sales Reports", "Opening Stock", "Set Opening"):
        chk(f"all-on: sidebar shows {label}", label in html, label)
    for path in ("/accountsReports/cash-ledger/", "/accountsReports/stock-summary/",
                 "/accountsReports/monthly-position/", "/sales-reports/",
                 "/opening-stock/", "/set-opening/"):
        resp = client.get(path)
        chk(f"all-on: GET {path} is 200", resp.status_code == 200, resp.status_code)
    resp = client.get("/accountsReports/stock-summary/")
    chk("all-on: CSV button present on stock reports",
        'id="download_csv"' in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/sale/sales/")
    chk("all-on: attachment widget on sale page",
        'id="attachments_panel"' in resp.content.decode("utf-8", "ignore"))

    # Whole groups disabled: sidebar entries vanish, URLs are blocked.
    set_features(company.pk, ["accounts_reports", "stock_reports", "monthly_reports",
                              "sales_reports", "opening_stock", "opening_cash"])
    resp = client.get("/home/")
    html = resp.content.decode("utf-8", "ignore")
    chk("groups-off: /home/ still 200", resp.status_code == 200, resp.status_code)
    for label in ("Accounts Reports", "Stock Reports", "Monthly Reports",
                  "Sales Reports", "Opening Stock", "Set Opening"):
        chk(f"groups-off: sidebar hides {label}", label not in html, label)
    chk("groups-off: sidebar keeps Sales entry", ">Sales" in html.replace("</i> ", ">"))
    for path in ("/accountsReports/cash-ledger/", "/accountsReports/stock-summary/",
                 "/accountsReports/monthly-position/"):
        resp = client.get(path)
        chk(f"groups-off: GET {path} redirects home",
            resp.status_code == 302 and resp["Location"].startswith("/home"),
            f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/sales-reports/")
    chk("groups-off: sales reports page redirects home",
        resp.status_code == 302 and resp["Location"].startswith("/home"),
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.get("/sales-reports/api/summary/?from=2026-01-01&to=2026-01-31")
    chk("groups-off: sales report API gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    resp = client.post("/accountsReports/trial-balance/", data="{}",
                       content_type="application/json")
    chk("groups-off: report data POST gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    body = resp.json()
    chk("groups-off: denial message is scrubbed and clear",
        body.get("status") == "denied" and "not enabled" in body.get("message", ""),
        body)
    for path in ("/opening-stock/", "/set-opening/"):
        resp = client.get(path)
        chk(f"groups-off: GET {path} redirects home",
            resp.status_code == 302 and resp["Location"].startswith("/home"),
            f"{resp.status_code} {resp.get('Location')}")

    # One sub-report disabled: page redirects to an enabled sibling, button hidden.
    set_features(company.pk, ["accounts_reports.cash_ledger"])
    resp = client.get("/accountsReports/cash-ledger/")
    chk("sub-off: disabled sub page redirects to enabled sibling",
        resp.status_code == 302
        and resp["Location"] == "/accountsReports/detailed-ledger/",
        f"{resp.status_code} {resp.get('Location')}")
    resp = client.post("/accountsReports/cash-ledger/", data="{}",
                       content_type="application/json")
    chk("sub-off: disabled sub data POST gets 403 JSON",
        resp.status_code == 403 and resp["Content-Type"].startswith("application/json"),
        resp.status_code)
    resp = client.get("/accountsReports/detailed-ledger/")
    html = resp.content.decode("utf-8", "ignore")
    chk("sub-off: sibling page is 200", resp.status_code == 200, resp.status_code)
    chk("sub-off: disabled report button hidden", 'id="btn-cash-ledger"' not in html)
    chk("sub-off: other report buttons still present", 'id="btn-ledger"' in html)
    resp = client.get("/home/")
    chk("sub-off: group sidebar entry survives",
        "Accounts Reports" in resp.content.decode("utf-8", "ignore"))

    # CSV/Excel export disabled: buttons disappear (PDF/Print stay).
    set_features(company.pk, ["excel_export"])
    resp = client.get("/accountsReports/stock-summary/")
    html = resp.content.decode("utf-8", "ignore")
    chk("csv-off: CSV button gone from stock reports", 'id="download_csv"' not in html)
    chk("csv-off: PDF button stays on stock reports", 'id="download_pdf"' in html)
    chk("csv-off: feature JSON object says export disabled",
        '"excel_export": {"enabled": false' in html)
    resp = client.get("/sales-reports/")
    html = resp.content.decode("utf-8", "ignore")
    chk("csv-off: CSV button gone from sales reports", 'id="sr-csv"' not in html)
    chk("csv-off: PDF button stays on sales reports", 'id="sr-pdf"' in html)
    resp = client.get("/month-close/")
    chk("csv-off: CSV button gone from month close",
        'id="mc-download-csv"' not in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/owner-equity/")
    chk("csv-off: CSV button gone from owner equity",
        'id="oe-download-csv"' not in resp.content.decode("utf-8", "ignore"))

    # Attachments disabled: widget hidden, endpoints blocked, uploads rejected.
    set_features(company.pk, ["attachments"])
    resp = client.get("/sale/sales/")
    chk("att-off: attachment widget hidden on sale page",
        'id="attachments_panel"' not in resp.content.decode("utf-8", "ignore"))
    resp = client.get("/attachments/sale/1/")
    chk("att-off: attachment endpoint blocked",
        resp.status_code in (302, 403), resp.status_code)

    set_features(company.pk, [])
    resp = client.get("/attachments/sale/1/")
    # Reaches the view again: 200 with metadata, or 404 JSON when invoice 1
    # does not exist on this tenant — either proves the block was lifted.
    chk("att-on again: attachment endpoint reachable",
        resp.status_code in (200, 404), resp.status_code)


def check_upload_guard(company):
    factory = RequestFactory()
    upload = SimpleUploadedFile("x.png", b"\x89PNG-not-really", content_type="image/png")
    request = factory.post("/sale/sales/", data={"attachment_image": upload})

    request.tenant_company = Company(name="x", disabled_features=["attachments"])
    try:
        validate_request_attachments(request)
        chk("upload with attachments off raises ValidationError", False, "no exception")
    except ValidationError as exc:
        chk("upload with attachments off raises ValidationError",
            "not enabled" in str(exc), exc)

    request.tenant_company = Company(name="x", disabled_features=[])
    try:
        validate_request_attachments(request)
        chk("upload with attachments on passes the feature gate", True)
    except ValidationError as exc:
        chk("upload with attachments on passes the feature gate", False, exc)


# ── Driver ───────────────────────────────────────────────────────────────────

def main():
    User = get_user_model()
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser is None:
        chk("a superuser exists", False, "no superuser available")
        return report()

    company = Company.objects.filter(is_active=True).exclude(schema_name="").order_by("id").first()
    if company is None:
        chk("an active company exists", False, "no active tenant companies")
        return report()

    snapshot = list(company.disabled_features or [])
    original_membership = None
    created_membership = False
    try:
        original_membership = superuser.membership
        if original_membership.company_id != company.pk:
            Membership.objects.filter(user=superuser).update(company=company)
    except Membership.DoesNotExist:
        Membership.objects.create(user=superuser, company=company)
        created_membership = True
    connection.close()

    try:
        check_registry_and_model()
        check_admin_form(Company.objects.get(pk=company.pk))
        check_admin_views(Company.objects.get(pk=company.pk))
        check_http(company)
        check_upload_guard(company)
    finally:
        connection.close()
        Company.objects.filter(pk=company.pk).update(disabled_features=snapshot)
        if created_membership:
            Membership.objects.filter(user=superuser).delete()
        elif original_membership is not None and original_membership.company_id != company.pk:
            Membership.objects.filter(user=superuser).update(
                company=original_membership.company_id
            )

    return report()


def report():
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} feature-flag checks passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
