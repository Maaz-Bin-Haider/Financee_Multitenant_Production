"""3A expansion only: retain the physical column for image-only rollback.

No rows, constraints, permissions, features, or tenant schemas are removed.
Only a guarded database default is added; the field/constraint are removed
from Django's migration state, not from PostgreSQL. Contraction is separate.
"""
from django.db import migrations


def set_compatibility_default(schema_editor, *, reverse=False):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        old_lock_timeout = cursor.fetchone()[0]
        cursor.execute("SHOW statement_timeout")
        old_statement_timeout = cursor.fetchone()[0]
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        # Hold the same lock ALTER TABLE needs while checking the old contract.
        # On contention or any failed precondition the atomic migration rolls
        # back; it must not guess or repair an unexpected production state.
        cursor.execute("LOCK TABLE public.tenancy_company IN ACCESS EXCLUSIVE MODE")
        cursor.execute("""
            SELECT format_type(a.atttypid, a.atttypmod), a.attnotnull,
                   pg_get_expr(d.adbin, d.adrelid)
              FROM pg_attribute a
              LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
             WHERE a.attrelid='public.tenancy_company'::regclass
               AND a.attname='inventory_mode' AND NOT a.attisdropped
        """)
        column = cursor.fetchone()
        expected_default = "'serial'::character varying" if reverse else None
        if column != ("character varying(16)", True, expected_default):
            raise RuntimeError("3A blocked: unexpected inventory-mode column contract")
        cursor.execute("""
            SELECT contype, convalidated, connoinherit, pg_get_expr(conbin, conrelid)
              FROM pg_constraint
             WHERE conrelid='public.tenancy_company'::regclass
               AND conname='tenancy_company_valid_inventory_mode'
        """)
        constraint = cursor.fetchone()
        if not constraint or constraint[:3] != ("c", True, False):
            raise RuntimeError("3A blocked: expected validated serial-only constraint required")
        expression = "".join(
            constraint[3].replace("(", "").replace(")", "").split()
        )
        if expression != "inventory_mode::text='serial'::text":
            raise RuntimeError("3A blocked: expected validated serial-only constraint required")
        cursor.execute("""
            SELECT EXISTS (SELECT 1 FROM public.tenancy_company
                            WHERE inventory_mode IS DISTINCT FROM 'serial')
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("3A blocked: registry contains non-serial values")
        if reverse:
            cursor.execute("ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode DROP DEFAULT")
        else:
            cursor.execute("ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode SET DEFAULT 'serial'")
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [old_lock_timeout])
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [old_statement_timeout])


def forwards(apps, schema_editor):
    set_compatibility_default(schema_editor)


def backwards(apps, schema_editor):
    set_compatibility_default(schema_editor, reverse=True)


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("tenancy", "0008_serial_only_company_creation")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forwards, backwards)],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="company", name="tenancy_company_valid_inventory_mode",
                ),
                migrations.RemoveField(model_name="company", name="inventory_mode"),
            ],
        ),
    ]
