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
            hardening_path=SQL_DIR / "quantity_production_hardening.sql",
            required_version=1,
            metadata_table="tenant_schema_metadata",
            runtime_enabled=False,
            required_tables=(
                "tenant_schema_metadata",
                "quantity_seed_registry",
                "document_sequences",
            ),
            required_sequences=("quantity_foundation_id_seq",),
            required_functions=(
                "quantity_schema_fingerprint",
                "quantity_assert_schema_family",
            ),
            rollout_files=("quantity_production_hardening.sql",),
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
