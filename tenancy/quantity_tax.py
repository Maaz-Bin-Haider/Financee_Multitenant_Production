"""Atomic adapter between quantity transaction lifecycles and schema v13."""

import copy
import json
from decimal import Decimal

from django.db import connection
from tenancy.models import Currency


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


MONEY_KEYS = {
    "subtotal_base", "line_discount_total_base",
    "invoice_discount_total_base", "tax_total_base", "total_base",
    "rounding_adjustment_base", "gross_base", "line_discount_base",
    "invoice_discount_base", "taxable_base", "tax_base", "line_total_base",
}


def calculate_and_transform(payload, *, price_key, company):
    """Return the immutable calculation and legacy-compatible net-price input."""
    calculation_input = copy.deepcopy(payload)
    source_lines = calculation_input.get("lines") or calculation_input.get("items")
    calculation_input["lines"] = [
        {**line, "unit_price": line.get(price_key, line.get("unit_price"))}
        for line in source_lines or []
    ]
    currency_code = (payload.get("transaction_currency_code")
                     or company.base_currency_id).upper()
    try:
        currency = Currency.objects.get(pk=currency_code, is_active=True)
    except Currency.DoesNotExist as exc:
        raise ValueError("Transaction currency is invalid or inactive.") from exc
    if currency_code == company.base_currency_id:
        if payload.get("exchange_rate") not in (None, "", 1, "1"):
            raise ValueError("Domestic documents must not provide an exchange rate.")
        rate = Decimal("1")
    else:
        try:
            rate = Decimal(str(payload.get("exchange_rate")))
        except Exception as exc:
            raise ValueError("A valid manual exchange rate is required.") from exc
        if rate <= 0 or rate != rate.quantize(Decimal("0.0000000001")):
            raise ValueError("Exchange rate must be positive with at most 10 decimals.")
    calculation_input["minor_units"] = currency.minor_units
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_calculate_document(%s::jsonb)",
            [json.dumps(calculation_input)],
        )
        foreign_calculation = _json(cursor.fetchone()[0])

    calculation = copy.deepcopy(foreign_calculation)
    for key in MONEY_KEYS:
        if key in calculation:
            calculation[key] = str(
                (Decimal(str(calculation[key])) * rate).quantize(Decimal("0.01"))
            )
    for line in calculation["lines"]:
        for key in MONEY_KEYS:
            if key in line:
                line[key] = str(
                    (Decimal(str(line[key])) * rate).quantize(Decimal("0.01"))
                )

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
    return calculation, transformed, foreign_calculation, currency_code, rate


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


def finalize_currency(
    kind, document_id, foreign_calculation, currency_code, rate, user_id
):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_finalize_currency_document(%s,%s,%s::jsonb,%s,%s,%s)",
            [
                kind, document_id, json.dumps(foreign_calculation),
                currency_code, str(rate), user_id,
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
        result = _json(cursor.fetchone()[0])
        cursor.execute(
            "SELECT quantity_apply_foreign_return(%s,%s,false)",
            [kind, return_id],
        )
        result.update(_json(cursor.fetchone()[0]))
        return result


def prepare_return_revision(kind, return_id, document_date, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_apply_foreign_return(%s,%s,true)",
            [kind, return_id],
        )
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
        result = cursor.fetchone()[0]
        cursor.execute(
            "SELECT quantity_apply_foreign_return(%s,%s,true)",
            [kind, return_id],
        )
        return result
