"""Phase 4 public currency catalogue and company accounting setup metadata."""

import django.db.models.deletion
from django.db import migrations, models


def seed_and_backfill(apps, schema_editor):
    Currency = apps.get_model("tenancy", "Currency")
    Company = apps.get_model("tenancy", "Company")

    # Kept in the application seed module so operators can idempotently refresh
    # the controlled catalogue with the matching management command.
    from tenancy.currencies import seed_currency_catalogue

    seed_currency_catalogue(Currency)
    Company.objects.filter(base_currency__isnull=True).update(
        base_currency_id="PKR",
        tax_environment="non_tax",
    )


def reverse_backfill(apps, schema_editor):
    # Schema reversal removes the Phase 4 fields/table. No business value was
    # converted, so there is no tenant-data reversal to perform.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0005_company_inventory_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="Currency",
            fields=[
                ("code", models.CharField(max_length=3, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("symbol", models.CharField(max_length=12)),
                ("minor_units", models.PositiveSmallIntegerField()),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Currency",
                "verbose_name_plural": "Currencies",
                "db_table": "tenancy_currency",
                "ordering": ["code"],
            },
        ),
        migrations.AddConstraint(
            model_name="currency",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__regex", "^[A-Z]{3}$")),
                name="tenancy_currency_valid_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="currency",
            constraint=models.CheckConstraint(
                condition=models.Q(("minor_units__lte", 4)),
                name="tenancy_currency_valid_minor_units",
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="base_currency",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="companies",
                to="tenancy.currency",
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="tax_environment",
            field=models.CharField(
                choices=[("non_tax", "Non-tax"), ("tax", "Tax-based")],
                default="non_tax",
                help_text=(
                    "Choose whether this company operates in a tax-based or "
                    "non-tax environment. It can be changed only before "
                    "financial activity."
                ),
                max_length=16,
            ),
        ),
        migrations.RunPython(seed_and_backfill, reverse_backfill),
        migrations.AlterField(
            model_name="company",
            name="base_currency",
            field=models.ForeignKey(
                default="PKR",
                help_text=(
                    "Accounting and reporting currency. It can be changed only "
                    "before the company has financial activity."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="companies",
                to="tenancy.currency",
            ),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.CheckConstraint(
                condition=models.Q(("tax_environment__in", ["tax", "non_tax"])),
                name="tenancy_company_valid_tax_environment",
            ),
        ),
    ]
