"""Atomic adapter between quantity transaction lifecycles and schema v13."""

import copy
import json
from decimal import Decimal

from django.db import connection


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def calculate_and_transform(payload, *, price_key):
    """Return the immutable calculation and legacy-compatible net-price input."""
    calculation_input = copy.deepcopy(payload)
    source_lines = calculation_input.get("lines") or calculation_input.get("items")
    calculation_input["lines"] = [
        {**line, "unit_price": line.get(price_key, line.get("unit_price"))}
        for line in source_lines or []
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_calculate_document(%s::jsonb)",
            [json.dumps(calculation_input)],
        )
        calculation = _json(cursor.fetchone()[0])

    transformed = copy.deepcopy(payload)
    target_lines = transformed.get("lines") or transformed.get("items") or []
    for line, result in zip(target_lines, calculation["lines"]):
        quantity = Decimal(str(line.get("quantity", line.get("qty"))))
        taxable = Decimal(str(result["taxable_base"]))
        line[price_key] = str((taxable / quantity).quantize(Decimal("0.000001")))
        line["unit_price"] = line[price_key]
    if "lines" in transformed:
        transformed["lines"] = target_lines
    else:
        transformed["items"] = target_lines
    return calculation, transformed


def finalize(kind, document_id, original_payload, calculation, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_finalize_tax_document(%s,%s,%s::jsonb,%s::jsonb,%s)",
            [
                kind, document_id, json.dumps(original_payload),
                json.dumps(calculation), user_id,
            ],
        )
        return _json(cursor.fetchone()[0])


def prepare_revision(kind, document_id, document_date, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_prepare_tax_revision(%s,%s,%s::date,%s)",
            [kind, document_id, document_date, user_id],
        )


def reverse(kind, document_id, reversal_date, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_reverse_tax_document(%s,%s,%s::date,%s)",
            [kind, document_id, reversal_date, user_id],
        )
        return cursor.fetchone()[0]


def catalog():
    with connection.cursor() as cursor:
        cursor.execute("SELECT quantity_tax_code_catalog(false)")
        return _json(cursor.fetchone()[0])


def finalize_return(kind, return_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_finalize_tax_return(%s,%s,%s)",
            [kind, return_id, user_id],
        )
        return _json(cursor.fetchone()[0])


def prepare_return_revision(kind, return_id, document_date, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_prepare_tax_return_revision(%s,%s,%s::date,%s)",
            [kind, return_id, document_date, user_id],
        )


def reverse_return(kind, return_id, reversal_date, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_reverse_tax_return(%s,%s,%s::date,%s)",
            [kind, return_id, reversal_date, user_id],
        )
        return cursor.fetchone()[0]
