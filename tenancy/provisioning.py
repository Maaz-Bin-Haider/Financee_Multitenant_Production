"""Transactional, schema-family-aware tenant provisioning."""

from django.db import connection, transaction

from .models import (
    INVENTORY_MODE_QUANTITY,
    PROVISIONING_FAILED,
    PROVISIONING_PROVISIONING,
    PROVISIONING_READY,
    Company,
)
from .schema_families import schema_family
from .utils import (
    PUBLIC_SCHEMA,
    schema_has_tables,
    search_path_for,
    validate_schema_name,
)


def _read_template(family_key: str) -> str:
    definition = schema_family(family_key)
    sql = definition.template_path.read_text(encoding="utf-8")
    if definition.key == INVENTORY_MODE_QUANTITY:
        # A fresh quantity tenant is composed from the stable base template
        # plus the family's current idempotent upgrade artifact. This keeps one
        # authoritative upgrade body for fresh and existing quantity schemas.
        sql += "\n" + definition.hardening_path.read_text(encoding="utf-8")
    return sql


def _assert_provisioned(cur, definition, base_currency_code):
    """Raise inside the provisioning transaction if the family is incomplete."""
    for table in definition.required_tables:
        cur.execute("SELECT to_regclass(%s)", [table])
        if cur.fetchone()[0] is None:
            raise RuntimeError("required_table_missing")
    for sequence in definition.required_sequences:
        cur.execute("SELECT to_regclass(%s)", [sequence])
        if cur.fetchone()[0] is None:
            raise RuntimeError("required_sequence_missing")
    for function in definition.required_functions:
        cur.execute(
            """
            SELECT 1 FROM information_schema.routines
             WHERE routine_schema = current_schema()
               AND routine_name = %s
             LIMIT 1
            """,
            [function],
        )
        if cur.fetchone() is None:
            raise RuntimeError("required_function_missing")

    if definition.key == INVENTORY_MODE_QUANTITY:
        cur.execute(
            """
            SELECT family, version, base_currency_code
              FROM tenant_schema_metadata
             WHERE id = true
            """
        )
        row = cur.fetchone()
        if (
            not row
            or row[0] != definition.key
            or int(row[1]) < definition.required_version
            or row[2] != base_currency_code
        ):
            raise RuntimeError("metadata_verification_failed")
    else:
        cur.execute("SELECT version FROM tenant_schema_version WHERE id = true")
        row = cur.fetchone()
        if not row or int(row[0]) < definition.required_version:
            raise RuntimeError("metadata_verification_failed")


def provision_schema(
    schema_name: str,
    force: bool = False,
    *,
    family: str = "serial",
    base_currency_code: str = "PKR",
) -> bool:
    """Create one physical tenant schema from its registered family template."""
    validate_schema_name(schema_name)
    definition = schema_family(family)

    if not force and schema_has_tables(schema_name):
        return False

    template_sql = _read_template(definition.key)
    quoted = connection.ops.quote_name(schema_name)
    tenant_path = search_path_for(schema_name)

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted}")
            cur.execute("SET check_function_bodies = false")
            cur.execute(f"SET search_path TO {tenant_path}")
            try:
                cur.execute(template_sql)
                if definition.key == INVENTORY_MODE_QUANTITY:
                    cur.execute(
                        """
                        UPDATE tenant_schema_metadata
                           SET base_currency_code = %s,
                               applied_at = CURRENT_TIMESTAMP
                         WHERE id = true
                        """,
                        [base_currency_code],
                    )
                _assert_provisioned(cur, definition, base_currency_code)
            finally:
                cur.execute(f"SET search_path TO {PUBLIC_SCHEMA}")
    return True


def provision_company(company: Company) -> bool:
    """Provision a company and persist a sanitized operational state."""
    if not company.schema_name:
        return False
    Company.objects.filter(pk=company.pk).update(
        provisioning_state=PROVISIONING_PROVISIONING,
        provisioning_error_code="",
    )
    try:
        created = provision_schema(
            company.schema_name,
            family=company.inventory_mode,
            base_currency_code=company.base_currency_id,
        )
    except Exception:
        Company.objects.filter(pk=company.pk).update(
            provisioning_state=PROVISIONING_FAILED,
            provisioning_error_code="schema_build_failed",
            is_active=False,
        )
        company.provisioning_state = PROVISIONING_FAILED
        company.provisioning_error_code = "schema_build_failed"
        company.is_active = False
        return False

    Company.objects.filter(pk=company.pk).update(
        provisioning_state=PROVISIONING_READY,
        provisioning_error_code="",
        is_active=True,
    )
    company.provisioning_state = PROVISIONING_READY
    company.provisioning_error_code = ""
    company.is_active = True
    return created
