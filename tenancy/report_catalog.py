"""Central, mode-aware report availability catalogue."""

from __future__ import annotations

from dataclasses import dataclass

from .models import INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL


@dataclass(frozen=True)
class QuantityReport:
    key: str
    label: str
    group: str
    feature: str
    permission: str


def _reports(group, feature, permission, entries):
    return tuple(
        QuantityReport(key, label, group, feature, permission)
        for key, label in entries
    )


QUANTITY_REPORTS = (
    *_reports("Accounts", "accounts_reports", "auth.view_accounts_reports_page", (
        ("trial_balance", "Trial Balance"),
        ("party_ledger", "Detailed Party Ledger"),
        ("cash_ledger", "Cash Ledger"),
        ("accounts_receivable", "Accounts Receivable"),
        ("accounts_payable", "Accounts Payable"),
        ("monthly_position", "Monthly Company Position"),
        ("monthly_income", "Monthly Income / Month End"),
        ("expense_report", "Expense Report"),
    )),
    *_reports("Stock", "stock_reports", "auth.view_stock_reports_page", (
        ("stock_summary", "Stock Summary"),
        ("stock_valuation", "FIFO Stock Valuation"),
        ("stock_movement", "Stock Movement Ledger"),
        ("item_history", "Item Transaction History"),
        ("last_purchase", "Last Purchase"),
        ("last_sale", "Last Sale"),
        ("low_stock", "Low Stock"),
        ("stock_aging", "Stock Aging"),
        ("fast_moving", "Fast Moving Stock"),
        ("slow_moving", "Slow Moving Stock"),
        ("inventory_integrity", "Inventory Integrity Exceptions"),
        ("inventory_reconciliation", "Inventory Movement Reconciliation"),
        ("valuation_reconciliation", "Inventory / Ledger Reconciliation"),
        ("transfer_report", "Warehouse Transfers"),
        ("count_adjustment", "Counts and Adjustments"),
    )),
    *_reports("Sales", "sales_reports", "auth.can_view_sales_summary", (
        ("daily_sales", "Daily Sales"),
        ("sales_summary", "Sales Summary"),
        ("product_profitability", "Product Profitability"),
        ("customer_profitability", "Customer Profitability"),
        ("sales_by_product", "Sales by Product"),
        ("sales_by_customer", "Sales by Customer"),
        ("sale_wise", "Sale-wise Profit"),
        ("sales_trend", "Sales Trend"),
        ("invoice_register", "Invoice Register"),
        ("margin_analysis", "Margin Analysis"),
        ("sale_return_analysis", "Sale Return Analysis"),
        ("return_rate", "Return Rate"),
    )),
    *_reports("Purchases", "purchase_reports", "auth.view_purchase", (
        ("purchase_register", "Purchase Register"),
        ("purchases_by_vendor", "Purchases by Vendor"),
        ("purchases_by_product", "Purchases by Product"),
        ("purchase_return_analysis", "Purchase Return Analysis"),
        ("purchase_price_variance", "Purchase Price Variance"),
    )),
)

QUANTITY_REPORT_MAP = {report.key: report for report in QUANTITY_REPORTS}
SERIAL_ONLY_REPORTS = frozenset({
    "stock_report", "serial_ledger", "serial_ledger_sold_flag",
    "serial_ledger_purchase_only", "serial_ledger_sale_only", "serial_details",
})


def available_reports(company):
    """Return only reports enabled for the trusted company mode and flags."""
    if not company or company.inventory_mode != INVENTORY_MODE_QUANTITY:
        return ()
    return tuple(
        report for report in QUANTITY_REPORTS
        if company.feature_enabled(report.feature)
    )


def report_available(company, key):
    if not company:
        return False
    if company.inventory_mode == INVENTORY_MODE_QUANTITY:
        report = QUANTITY_REPORT_MAP.get(key)
        return bool(report and company.feature_enabled(report.feature))
    if company.inventory_mode == INVENTORY_MODE_SERIAL:
        return key not in QUANTITY_REPORT_MAP
    return False
