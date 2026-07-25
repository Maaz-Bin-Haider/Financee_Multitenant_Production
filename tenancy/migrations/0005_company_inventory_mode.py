# Add the permanent tenant inventory mode. The default/backfill is "serial",
# preserving every existing company and schema exactly as they are.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0004_company_feature_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="inventory_mode",
            field=models.CharField(
                choices=[
                    ("serial", "Serial-number based"),
                    ("quantity", "Quantity based"),
                ],
                default="serial",
                help_text=(
                    "Permanent inventory model for this company. Existing "
                    "companies are serial-number based. Quantity-company "
                    "provisioning is enabled only after its separate schema "
                    "family is deployed."
                ),
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.CheckConstraint(
                condition=models.Q(inventory_mode__in=["serial", "quantity"]),
                name="tenancy_company_valid_inventory_mode",
            ),
        ),
    ]
