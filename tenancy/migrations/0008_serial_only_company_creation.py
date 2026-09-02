"""Close every supported and database-level quantity-company creation path."""

from django.db import migrations, models


def require_serial_registry(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    conflicts = list(
        Company.objects.exclude(inventory_mode="serial")
        .order_by("pk")
        .values_list("pk", flat=True)[:21]
    )
    if conflicts:
        displayed = conflicts[:20]
        suffix = " (more exist)" if len(conflicts) > 20 else ""
        raise RuntimeError(
            "serial-only migration blocked by non-serial Company IDs: "
            f"{displayed}{suffix}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0007_company_provisioning_state"),
    ]

    operations = [
        migrations.RunPython(require_serial_registry, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="company",
            name="tenancy_company_valid_inventory_mode",
        ),
        migrations.AlterField(
            model_name="company",
            name="inventory_mode",
            field=models.CharField(
                choices=[("serial", "Serial-number based")],
                default="serial",
                help_text="All companies use serial-number based inventory.",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.CheckConstraint(
                condition=models.Q(inventory_mode="serial"),
                name="tenancy_company_valid_inventory_mode",
            ),
        ),
    ]
