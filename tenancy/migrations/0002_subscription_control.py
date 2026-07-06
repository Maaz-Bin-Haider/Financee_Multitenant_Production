"""
Subscription control (public schema only — no tenant business tables touched).

Adds the manual-billing subscription fields to Company and the
SubscriptionPayment audit log. Existing companies get paid_until = NULL,
which means "subscription not enforced", so nothing is blocked by applying
this migration.
"""
import datetime

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="is_suspended",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Manual override: immediately block every user of this company, "
                    "regardless of the paid-until date. Recording a payment lifts it."
                ),
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="paid_until",
            field=models.DateField(
                blank=True,
                null=True,
                help_text=(
                    "Subscription is paid up to this date (inclusive). Leave empty to "
                    "disable subscription enforcement for this company."
                ),
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="grace_days",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text=(
                    "Days of continued access after the paid-until date before the "
                    "company is blocked automatically."
                ),
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="warn_days_before",
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text=(
                    "Show the company's users a renewal warning banner this many days "
                    "before the paid-until date."
                ),
            ),
        ),
        migrations.CreateModel(
            name="SubscriptionPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "date_received",
                    models.DateField(
                        default=datetime.date.today,
                        help_text="The day the money actually arrived.",
                    ),
                ),
                (
                    "months_covered",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="How many months of service this payment buys.",
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "paid_until_after",
                    models.DateField(
                        editable=False,
                        null=True,
                        help_text="The company's paid-until date right after this payment was applied.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription_payments",
                        to="tenancy.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "tenancy_subscription_payment",
                "verbose_name": "Subscription payment",
                "verbose_name_plural": "Subscription payments",
                "ordering": ["-date_received", "-id"],
            },
        ),
    ]
