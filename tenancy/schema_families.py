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
            hardening_path=SQL_DIR / "quantity_fifo_engine.sql",
            required_version=5,
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
            ),
            rollout_files=("quantity_fifo_engine.sql",),
            enabled_path_prefixes=(
                "/items/quantity/",
                "/warehouses/quantity/",
            ),
            bootstrap_paths=(
                SQL_DIR / "quantity_item_master.sql",
                SQL_DIR / "quantity_warehouse_foundation.sql",
                SQL_DIR / "quantity_fifo_engine.sql",
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
