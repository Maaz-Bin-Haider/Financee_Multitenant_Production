"""Render Financee's existing SQL report without recomputing financial totals."""
import csv
import io
import json
from decimal import Decimal
from django.db import connection
from django.utils.html import escape

COLUMNS = (
    ('sale_date', 'Sale date', 'text'), ('customer_name', 'Customer', 'text'),
    ('item_name', 'Item', 'text'), ('serial_number', 'Serial #', 'text'),
    ('serial_comment', 'Comment', 'text'), ('vendor_name', 'Supplier', 'text'),
    ('sale_price', 'Sale price', 'money'), ('purchase_price', 'Purchase cost', 'money'),
    ('profit_loss', 'Profit / loss', 'money'), ('profit_loss_percent', 'Markup %', 'percent'),
)


def fetch_report(day):
    with connection.cursor() as cursor:
        cursor.execute('SELECT sale_wise_profit_json(%s,%s)::text', [day, day])
        return json.loads(cursor.fetchone()[0], parse_float=Decimal)


def money(value, company):
    # SQL report values have two places even for a zero-decimal currency.
    # Preserve those source cents rather than hiding a financial difference.
    places=max(2,company.base_currency.minor_units)
    return f'{company.base_currency_id} {Decimal(str(value or 0)):,.{places}f}'


def percent(value):
    return '—' if value is None else f'{Decimal(str(value)):,.2f}%'


def subject(report, day, company):
    totals = report['totals']
    suffix = 'no sales' if not totals['units'] else f"{totals['units']} units, profit {money(totals['profit'], company)}"
    return f'{company.name} · Sale-wise Profit · {day.isoformat()} · {suffix}'


def build_text(report, day, company):
    totals = report['totals']
    return '\n'.join((f'{company.name} — Sale-wise Profit — {day.isoformat()}',
        f"Units: {totals['units']}", f"Sales: {money(totals['revenue'], company)}",
        f"Purchase cost: {money(totals['cost'], company)}", f"Profit: {money(totals['profit'], company)}",
        f"Margin on revenue: {percent(totals['margin_pct'])}",
        'Returned serials are excluded, matching the Sale-wise Profit screen.',
        'No sales for this day.' if not totals['units'] else 'Full serial details are attached as CSV.'))


def build_csv(report, day, company):
    def safe(value):
        # Untrusted party/item/comment text must not become spreadsheet formulas.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'" + value
        return value
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow([safe(company.name), 'Sale-wise Profit', day.isoformat(), company.base_currency_id])
    writer.writerow([label for _, label, _ in COLUMNS])
    for row in report['rows']:
        writer.writerow([safe(row.get(key)) for key, _, _ in COLUMNS])
    totals = report['totals']
    writer.writerow(['TOTAL', f"{totals['units']} units", '', '', '', '',
                     totals['revenue'], totals['cost'], totals['profit'], ''])
    writer.writerow(['Margin on revenue', totals['margin_pct']])
    return buffer.getvalue()


def build_html(report, day, company, zone):
    def cell(value, tag='td'):
        return f'<{tag} style="padding:9px;border-bottom:1px solid #dce3ed;text-align:left">{escape(value)}</{tag}>'
    head = ''.join(cell(label, 'th') for _, label, _ in COLUMNS)
    body = []
    for row in report['rows']:
        cells = []
        for key, _, kind in COLUMNS:
            value = row.get(key)
            value = money(value, company) if kind == 'money' else percent(value) if kind == 'percent' else value or '—'
            cells.append(cell(value))
        shade = '#fef2f2' if Decimal(str(row.get('profit_loss') or 0)) < 0 else '#ffffff'
        body.append(f'<tr style="background:{shade}">{"".join(cells)}</tr>')
    if not body:
        body = ['<tr><td colspan="10" style="padding:24px">No sales for this business day.</td></tr>']
    return (f'<!doctype html><html><head><meta charset="utf-8"></head>'
        f'<body style="background:#eef2f7;font:14px Arial,sans-serif;color:#142540;padding:20px">'
        f'<table role="presentation" style="background:white;width:100%;max-width:1100px;margin:auto">'
        f'<tr><td style="padding:20px;background:#142540;color:white">'
        f'<h1 style="font-size:22px">{escape(company.name)} · Sale-wise Profit</h1>'
        f'{escape(day.isoformat())} · {escape(zone)} · {escape(company.base_currency_id)}</td></tr>'
        f'<tr><td style="padding:20px"><pre style="white-space:pre-wrap;font:14px Arial,sans-serif">'
        f'{escape(build_text(report, day, company))}</pre></td></tr>'
        f'<tr><td><table style="border-collapse:collapse;width:100%;font-size:12px">'
        f'<thead style="background:#e8eef7"><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></td></tr>'
        f'<tr><td style="padding:18px;color:#50617b">Financee · Row markup uses purchase cost; '
        f'total margin uses revenue. Figures match the existing report; no GST adjustment is applied.</td></tr>'
        f'</table></body></html>')
