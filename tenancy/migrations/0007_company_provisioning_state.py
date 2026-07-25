"""Phase 5 company schema-provisioning lifecycle metadata."""

from django.db import migrations, models


def mark_existing_ready(apps, schema_editor):
    Company = apps.get_model("tenancy", "Company")
    Company.objects.update(
        provisioning_state="ready",
        provisioning_error_code="",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0006_currency_company_setup"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="provisioning_error_code",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Sanitized provisioning failure category; never contains "
                    "SQL or secrets."
                ),
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="provisioning_state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("provisioning", "Provisioning"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                default="pending",
                help_text="Operational state of the physical tenant schema.",
                max_length=16,
            ),
        ),
        migrations.RunPython(mark_existing_ready, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    provisioning_state__in=[
                        "pending", "provisioning", "ready", "failed",
                    ]
                ),
                name="tenancy_company_valid_provisioning_state",
            ),
        ),
    ]
