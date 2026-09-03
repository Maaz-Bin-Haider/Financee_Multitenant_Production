"""Central schema-family registry.

All template, hardening, version, and fingerprint selection lives here. Views,
commands, and provisioning must never construct family-specific paths ad hoc.
"""

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from .models import INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL

SQL_DIR = Path(__file__).resolve().parent / "sql"


@dataclass(frozen=True)
class SchemaFamily:
    key: str
    template_path: Path
    hardening_path: Path
    required_version: int
    metadata_table: str
    runtime_enabled: bool
    required_tables: tuple[str, ...]
    required_sequences: tuple[str, ...] = ()
    required_functions: tuple[str, ...] = ()
    rollout_files: tuple[str, ...] = ()
    enabled_path_prefixes: tuple[str, ...] = ()
    bootstrap_paths: tuple[Path, ...] = ()


def _families():
    return {
        INVENTORY_MODE_SERIAL: SchemaFamily(
            key=INVENTORY_MODE_SERIAL,
            template_path=SQL_DIR / "tenant_template.sql",
            hardening_path=SQL_DIR / "production_hardening.sql",
            required_version=getattr(settings, "TENANT_SCHEMA_VERSION", 6),
            metadata_table="tenant_schema_version",
            runtime_enabled=True,
            required_tables=(
                "tenant_schema_version", "items", "parties",
                "journalentries", "journallines",
            ),
            rollout_files=(
                "production_hardening.sql",
                "tenant_indexes.sql",
                "fix_sale_return_lifecycle_guards.sql",
                "fix_transaction_integrity_guards.sql",
                "fix_tenant_drift.sql",
                "fix_cash_party_port.sql",
                "add_document_attachments.sql",
            ),
        ),
        INVENTORY_MODE_QUANTITY: SchemaFamily(
            key=INVENTORY_MODE_QUANTITY,
            template_path=SQL_DIR / "quantity_tenant_template.sql",
            hardening_path=SQL_DIR / "quantity_platform_controls.sql",
            required_version=22,
            metadata_table="tenant_schema_metadata",
            runtime_enabled=False,
            required_tables=(
                "tenant_schema_metadata",
                "quantity_seed_registry",
                "document_sequences",
                "chart_of_accounts",
                "journal_entries",
                "journal_lines",
                "units_of_measure",
                "products",
                "product_variants",
                "variant_transaction_registry",
                "warehouses",
                "warehouse_reference_registry",
                "stock_movements",
                "stock_balances",
                "fifo_layers",
                "fifo_allocations",
                "opening_stock_documents",
                "opening_stock_lines",
                "purchase_invoices",
                "purchase_lines",
                "purchase_revisions",
                "sale_invoices",
                "sale_lines",
                "sale_revisions",
                "sale_return_invoices",
                "sale_return_lines",
                "sale_return_cost_restorations",
                "sale_return_revisions",
                "purchase_return_invoices",
                "purchase_return_lines",
                "purchase_return_source_allocations",
                "purchase_return_revisions",
                "warehouse_transfers",
                "warehouse_transfer_lines",
                "warehouse_transfer_cost_segments",
                "warehouse_transfer_revisions",
                "physical_counts",
                "physical_count_lines",
                "inventory_adjustments",
                "inventory_adjustment_lines",
                "tax_codes",
                "foreign_payments",
                "payment_allocations",
                "foreign_receipts",
                "receipt_allocations",
                "parties",
                "payments",
                "receipts",
                "contra_entries",
                "opening_cash",
                "owner_equity_transactions",
                "period_closes",
                "document_attachments",
                "quantity_audit_events",
            ),
            required_sequences=(
                "quantity_foundation_id_seq",
                "chart_of_accounts_account_id_seq",
                "journal_entries_journal_id_seq",
                "journal_lines_line_id_seq",
                "units_of_measure_unit_id_seq",
                "products_product_id_seq",
                "product_variants_variant_id_seq",
                "variant_transaction_registry_reference_id_seq",
                "warehouses_warehouse_id_seq",
                "warehouse_reference_registry_reference_id_seq",
                "stock_movements_movement_id_seq",
                "fifo_layers_layer_id_seq",
                "fifo_allocations_allocation_id_seq",
                "inventory_effective_sequence_seq",
                "opening_stock_documents_opening_stock_id_seq",
                "opening_stock_lines_opening_stock_line_id_seq",
                "purchase_invoices_purchase_invoice_id_seq",
                "purchase_lines_purchase_line_id_seq",
                "purchase_revisions_purchase_revision_id_seq",
                "sale_invoices_sale_invoice_id_seq",
                "sale_lines_sale_line_id_seq",
                "sale_revisions_sale_revision_id_seq",
                "sale_return_invoices_sale_return_id_seq",
                "sale_return_lines_sale_return_line_id_seq",
                "sale_return_cost_restorations_restoration_id_seq",
                "sale_return_revisions_sale_return_revision_id_seq",
                "purchase_return_invoices_purchase_return_id_seq",
                "purchase_return_lines_purchase_return_line_id_seq",
                "purchase_return_source_allocations_source_allocation_id_seq",
                "purchase_return_revisions_purchase_return_revision_id_seq",
                "warehouse_transfers_transfer_id_seq",
                "warehouse_transfer_lines_transfer_line_id_seq",
                "warehouse_transfer_cost_segments_segment_id_seq",
                "warehouse_transfer_revisions_transfer_revision_id_seq",
                "physical_counts_count_id_seq",
                "physical_count_lines_count_line_id_seq",
                "inventory_adjustments_adjustment_id_seq",
                "inventory_adjustment_lines_adjustment_line_id_seq",
                "tax_codes_tax_code_id_seq",
                "foreign_payments_payment_id_seq",
                "payment_allocations_allocation_id_seq",
                "foreign_receipts_receipt_id_seq",
                "receipt_allocations_allocation_id_seq",
                "parties_party_id_seq",
                "payments_payment_id_seq",
                "receipts_receipt_id_seq",
                "contra_entries_contra_id_seq",
                "opening_cash_opening_cash_id_seq",
                "owner_equity_transactions_txn_id_seq",
                "period_closes_period_close_id_seq",
                "document_attachments_attachment_id_seq",
                "quantity_audit_events_event_id_seq",
            ),
            required_functions=(
                "quantity_schema_fingerprint",
                "quantity_assert_schema_family",
                "quantity_next_document_number",
                "quantity_post_journal",
                "quantity_reverse_journal",
                "quantity_account_lookup",
                "quantity_create_product",
                "quantity_update_product",
                "quantity_create_variant",
                "quantity_update_variant",
                "quantity_item_catalog",
                "quantity_suggest_sku",
                "quantity_validate_quantity",
                "quantity_create_warehouse",
                "quantity_update_warehouse",
                "quantity_delete_warehouse",
                "quantity_warehouse_lookup",
                "quantity_default_warehouse",
                "quantity_post_stock_movement",
                "quantity_reverse_stock_movement",
                "quantity_replay_inventory",
                "quantity_stock_availability",
                "quantity_inventory_reconciliation",
                "quantity_lock_inventory_pairs",
                "quantity_create_opening_stock",
                "quantity_opening_stock_list",
                "quantity_opening_stock_details",
                "quantity_reverse_opening_stock",
                "quantity_opening_balance_status",
                "quantity_reclassify_opening_balance",
                "quantity_create_purchase",
                "quantity_update_purchase",
                "quantity_reverse_purchase",
                "quantity_purchase_details",
                "quantity_purchase_navigate",
                "quantity_purchase_summary",
                "quantity_create_sale",
                "quantity_update_sale",
                "quantity_reverse_sale",
                "quantity_sale_details",
                "quantity_sale_navigate",
                "quantity_sale_summary",
                "quantity_create_sale_return",
                "quantity_update_sale_return",
                "quantity_reverse_sale_return",
                "quantity_sale_return_details",
                "quantity_sale_return_sources",
                "quantity_sale_return_navigate",
                "quantity_sale_return_summary",
                "quantity_create_purchase_return",
                "quantity_update_purchase_return",
                "quantity_reverse_purchase_return",
                "quantity_purchase_return_details",
                "quantity_purchase_return_sources",
                "quantity_purchase_return_navigate",
                "quantity_purchase_return_summary",
                "quantity_create_transfer",
                "quantity_update_transfer",
                "quantity_reverse_transfer",
                "quantity_transfer_details",
                "quantity_transfer_navigate",
                "quantity_transfer_summary",
                "quantity_create_physical_count",
                "quantity_approve_physical_count",
                "quantity_reverse_physical_count",
                "quantity_physical_count_details",
                "quantity_physical_count_navigate",
                "quantity_physical_count_summary",
                "quantity_upsert_tax_code",
                "quantity_tax_code_catalog",
                "quantity_calculate_document",
                "quantity_finalize_tax_document",
                "quantity_prepare_tax_revision",
                "quantity_reverse_tax_document",
                "quantity_finalize_tax_return",
                "quantity_prepare_tax_return_revision",
                "quantity_reverse_tax_return",
                "quantity_default_document_currency",
                "quantity_finalize_currency_document",
                "quantity_settle_foreign_purchase",
                "quantity_settle_foreign_sale",
                "quantity_apply_foreign_return",
                "quantity_currency_report",
                "quantity_report_filters",
                "quantity_run_report",
                "quantity_dashboard",
                "quantity_assert_open_date",
                "add_party_from_json",
                "get_party_balance_by_name",
                "make_payment",
                "make_receipt",
                "make_contra",
                "set_opening_cash_from_json",
                "add_owner_equity_txn",
                "preview_period_close",
                "close_period_from_json",
                "reverse_period_close",
                "quantity_audit_log",
            ),
            rollout_files=(
                "quantity_platform_controls.sql",
                "quantity_reports_dashboards.sql",
            ),
            # Retained only so Phase 3 can identify and safely clean historical
            # schemas. No request path may activate this retired runtime.
            enabled_path_prefixes=(),
            bootstrap_paths=(
                SQL_DIR / "quantity_item_master.sql",
                SQL_DIR / "quantity_warehouse_foundation.sql",
                SQL_DIR / "quantity_fifo_engine.sql",
                SQL_DIR / "quantity_opening_stock.sql",
                SQL_DIR / "quantity_purchases.sql",
                SQL_DIR / "quantity_sales.sql",
                SQL_DIR / "quantity_sale_returns.sql",
                SQL_DIR / "quantity_purchase_returns.sql",
                SQL_DIR / "quantity_warehouse_transfers.sql",
                SQL_DIR / "quantity_counts_adjustments.sql",
                SQL_DIR / "quantity_tax_discounts.sql",
                SQL_DIR / "quantity_currency_settlements.sql",
                SQL_DIR / "quantity_financial_modules.sql",
                SQL_DIR / "quantity_platform_controls.sql",
                SQL_DIR / "quantity_reports_dashboards.sql",
            ),
        ),
    }


def schema_family(family_key: str) -> SchemaFamily:
    try:
        return _families()[family_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported schema family: {family_key!r}") from exc


def all_schema_families():
    return tuple(_families().values())


def family_for_sql_file(sql_path: str) -> str:
    """Resolve and validate the family owning a controlled rollout SQL file."""
    name = Path(sql_path).name
    matches = [
        family.key
        for family in all_schema_families()
        if name in family.rollout_files
    ]
    if len(matches) != 1:
        raise ValueError(
            f"SQL file {name!r} is not registered to exactly one schema family."
        )
    return matches[0]
