"""
tenancy.features
================
Per-company feature flags, controlled from the admin panel.

The operator can switch whole report groups (Accounts Reports, Stock Reports,
Monthly Reports, Sales Reports, Opening Stock, Opening Cash), every individual
sub-report inside a group, CSV/Excel export, and document attachments on/off
for a specific company. Disabled features disappear from the tenant UI
(sidebar links, in-page report buttons, export buttons, attachment widget)
and their URLs are blocked by ``TenantSchemaMiddleware``.

Storage: ``Company.disabled_features`` (public schema, JSON list of disabled
feature keys). An empty list — the default — means everything is enabled, so
existing companies are unaffected. A key is either a group (``"stock_reports"``)
or ``"group.sub"`` (``"stock_reports.serial_ledger"``). Disabling a group
disables all of its sub-features regardless of their own keys.

No tenant SQL is involved: like subscription control, this is registry data.
"""

# ── Feature registry ────────────────────────────────────────────────────────
# group key -> {"label": ..., "subs": {sub key -> label}}. Groups without subs
# are single switches. Keep keys stable: they are persisted on Company rows.
FEATURE_GROUPS = {
    "accounts_reports": {
        "label": "Accounts Reports",
        "subs": {
            # Key names follow the URLs; labels follow the UI buttons
            # (/detailed-ledger/ renders as "Party Ledger", /detailed-ledger2/
            # as "Detailed Ledger").
            "detailed_ledger": "Party Ledger",
            "detailed_ledger2": "Detailed Ledger",
            "cash_ledger": "Cash Ledger",
            "trial_balance": "Trial Balance",
            "accounts_receivable": "Accounts Receivable",
            "accounts_payable": "Accounts Payable",
        },
    },
    "stock_reports": {
        "label": "Stock Reports",
        "subs": {
            # Key names follow the URLs; labels follow the UI buttons
            # (/stock-summary/ renders as "Stock Report", /stock-report/ as
            # "Stock Serial Wise").
            "stock_summary": "Stock Report",
            "stock_report": "Stock Serial Wise",
            "serial_ledger": "Serial Ledger",
            "serial_ledger_sold_flag": "Serial Ledger Sold Flag",
            "serial_ledger_purchase_only": "Serial Ledger Purchase",
            "serial_ledger_sale_only": "Serial Ledger Sale",
            "item_history": "Item History",
            "item_detail": "Item Detail",
            "stock_worth": "Stock Worth Report",
            "item_last_purchase": "Item Last Purchase",
            "item_last_sale": "Items Last Sale",
        },
    },
    "monthly_reports": {
        "label": "Monthly Reports",
        "subs": {
            "monthly_position": "Company Position",
            "monthly_income": "Income Statement",
        },
    },
    "sales_reports": {
        "label": "Sales Reports",
        "subs": {
            "summary": "Sales Summary",
            "product_profitability": "Product Profitability",
            "customer_profitability": "Customer Profitability",
            "sales_by_product": "Sales by Product",
            "sales_by_customer": "Sales by Customer",
            "sale_wise": "Sale-wise Profit",
            "trend": "Sales Trend Dashboard",
            "invoice_register": "Invoice Register",
        },
    },
    "opening_stock": {"label": "Opening Stock", "subs": {}},
    "opening_cash": {"label": "Opening Cash (Set Opening)", "subs": {}},
    "excel_export": {"label": "CSV / Excel export buttons", "subs": {}},
    "attachments": {"label": "Document attachments (image / PDF upload)", "subs": {}},
    "quantity_controls": {
        "label": "Quantity inventory controls",
        "modes": ("quantity",),
        "subs": {
            "warehouses": "Warehouses",
            "transfers": "Warehouse transfers",
            "counts": "Physical counts and adjustments",
            "tax": "Tax-code administration",
            "audit": "Immutable audit log",
        },
    },
}


def all_feature_keys():
    """Every valid key: groups plus group.sub."""
    keys = []
    for group, spec in FEATURE_GROUPS.items():
        keys.append(group)
        keys.extend(f"{group}.{sub}" for sub in spec["subs"])
    return keys


# ── URL enforcement map ─────────────────────────────────────────────────────
# Longest-prefix match of request.path -> feature key. Sub-report pages double
# as their own AJAX data endpoints (GET renders the shared template, POST
# returns JSON), so one prefix covers both.
FEATURE_PATH_PREFIXES = (
    ("/accountsReports/detailed-ledger2/", "accounts_reports.detailed_ledger2"),
    ("/accountsReports/detailed-ledger/", "accounts_reports.detailed_ledger"),
    ("/accountsReports/cash-ledger/", "accounts_reports.cash_ledger"),
    ("/accountsReports/trial-balance/", "accounts_reports.trial_balance"),
    ("/accountsReports/accounts-receivable/", "accounts_reports.accounts_receivable"),
    ("/accountsReports/accounts-payable/", "accounts_reports.accounts_payable"),
    ("/accountsReports/stock-summary/", "stock_reports.stock_summary"),
    ("/accountsReports/stock-report/", "stock_reports.stock_report"),
    ("/accountsReports/serial-ledger-sold-flag/", "stock_reports.serial_ledger_sold_flag"),
    ("/accountsReports/serial-ledger-purchase-only/", "stock_reports.serial_ledger_purchase_only"),
    ("/accountsReports/serial-ledger-sale-only/", "stock_reports.serial_ledger_sale_only"),
    ("/accountsReports/serial-ledger/", "stock_reports.serial_ledger"),
    ("/accountsReports/item-history/", "stock_reports.item_history"),
    ("/accountsReports/item-detail/", "stock_reports.item_detail"),
    ("/accountsReports/stock-worth-report/", "stock_reports.stock_worth"),
    ("/accountsReports/item-last-purchase/", "stock_reports.item_last_purchase"),
    ("/accountsReports/item-last-sale/", "stock_reports.item_last_sale"),
    ("/accountsReports/monthly-position/", "monthly_reports.monthly_position"),
    ("/accountsReports/monthly-income/", "monthly_reports.monthly_income"),
    ("/sales-reports/api/summary/", "sales_reports.summary"),
    ("/sales-reports/api/product-profitability/", "sales_reports.product_profitability"),
    ("/sales-reports/api/customer-profitability/", "sales_reports.customer_profitability"),
    ("/sales-reports/api/sales-by-product/", "sales_reports.sales_by_product"),
    ("/sales-reports/api/sales-by-customer/", "sales_reports.sales_by_customer"),
    ("/sales-reports/api/sale-wise/", "sales_reports.sale_wise"),
    ("/sales-reports/api/trend/", "sales_reports.trend"),
    ("/sales-reports/api/invoice-register/", "sales_reports.invoice_register"),
    ("/sales-reports/", "sales_reports"),
    ("/opening-stock/", "opening_stock"),
    ("/set-opening/", "opening_cash"),
    ("/attachments/", "attachments"),
    ("/warehouses/quantity/", "quantity_controls.warehouses"),
    ("/transfers/", "quantity_controls.transfers"),
    ("/physical-counts/", "quantity_controls.counts"),
    ("/purchase/quantity-tax-codes/", "quantity_controls.tax"),
    ("/quantity-audit/", "quantity_controls.audit"),
)


def feature_for_path(path):
    """Feature key guarding this path, or None when the path is unrestricted."""
    for prefix, key in FEATURE_PATH_PREFIXES:
        if path.startswith(prefix):
            return key
    return None


# ── Fallback pages ──────────────────────────────────────────────────────────
# When a user lands on a disabled sub-report PAGE (plain GET) we redirect to
# the first enabled sibling of the same group instead of erroring, so sidebar
# entry points keep working when only some subs are disabled.
GROUP_LANDING_PATHS = {
    "accounts_reports": (
        ("cash_ledger", "/accountsReports/cash-ledger/"),
        ("detailed_ledger", "/accountsReports/detailed-ledger/"),
        ("detailed_ledger2", "/accountsReports/detailed-ledger2/"),
        ("trial_balance", "/accountsReports/trial-balance/"),
        ("accounts_receivable", "/accountsReports/accounts-receivable/"),
        ("accounts_payable", "/accountsReports/accounts-payable/"),
    ),
    "stock_reports": (
        ("stock_summary", "/accountsReports/stock-summary/"),
        ("stock_report", "/accountsReports/stock-report/"),
        ("serial_ledger", "/accountsReports/serial-ledger/"),
        ("serial_ledger_sold_flag", "/accountsReports/serial-ledger-sold-flag/"),
        ("serial_ledger_purchase_only", "/accountsReports/serial-ledger-purchase-only/"),
        ("serial_ledger_sale_only", "/accountsReports/serial-ledger-sale-only/"),
        ("item_history", "/accountsReports/item-history/"),
        ("item_detail", "/accountsReports/item-detail/"),
        ("stock_worth", "/accountsReports/stock-worth-report/"),
        ("item_last_purchase", "/accountsReports/item-last-purchase/"),
        ("item_last_sale", "/accountsReports/item-last-sale/"),
    ),
    "monthly_reports": (
        ("monthly_position", "/accountsReports/monthly-position/"),
        ("monthly_income", "/accountsReports/monthly-income/"),
    ),
}


def enabled_sibling_path(company, group):
    """First enabled sub-report page of the group, or None."""
    for sub, path in GROUP_LANDING_PATHS.get(group, ()):
        if company.feature_enabled(f"{group}.{sub}"):
            return path
    return None


def features_map(company=None):
    """
    Nested {group: {"enabled": bool, "subs": {sub: bool}}} for templates and
    the frontend. With no company (public pages, no membership) everything is
    enabled so shared screens render normally.
    """
    result = {}
    for group, spec in FEATURE_GROUPS.items():
        group_on = company.feature_enabled(group) if company else True
        result[group] = {
            "enabled": group_on,
            "applicable": (
                company is None
                or not spec.get("modes")
                or company.inventory_mode in spec["modes"]
            ),
            "subs": {
                sub: (company.feature_enabled(f"{group}.{sub}") if company else True)
                for sub in spec["subs"]
            },
        }
    return result
