# Per-company feature flags: a JSON list of disabled feature keys
# (see tenancy/features.py). Default [] keeps every feature enabled for
# existing companies, so applying this migration changes nothing for anyone.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0003_subscription_emails"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="disabled_features",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Feature keys switched off for this company.",
            ),
        ),
    ]
