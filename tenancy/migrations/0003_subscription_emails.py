"""
Subscription email notifications (public schema only).

Adds Company.contact_email (the company's billing address), the
BillingSettings singleton (operator SMTP account + contact details, editable
from the admin), and the SubscriptionEmailLog audit/dedup table.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0002_subscription_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="contact_email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                help_text=(
                    "The company's billing email. Subscription expiry/suspension "
                    "notifications are sent here (not to individual users). Leave "
                    "empty to skip email notifications for this company."
                ),
            ),
        ),
        migrations.CreateModel(
            name="BillingSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "sender_name",
                    models.CharField(
                        default="Financee",
                        help_text="Display name on outgoing emails.",
                        max_length=100,
                    ),
                ),
                (
                    "sender_email",
                    models.EmailField(
                        blank=True,
                        help_text="The email account subscription notifications are sent from.",
                        max_length=254,
                    ),
                ),
                (
                    "app_password",
                    models.CharField(
                        blank=True,
                        help_text="SMTP app password for the sender account (e.g. a Gmail app password).",
                        max_length=128,
                    ),
                ),
                ("smtp_host", models.CharField(default="smtp.gmail.com", max_length=120)),
                ("smtp_port", models.PositiveIntegerField(default=587)),
                ("use_tls", models.BooleanField(default=True)),
                (
                    "emails_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Master switch: untick to stop all subscription emails.",
                    ),
                ),
                (
                    "whatsapp_number",
                    models.CharField(
                        blank=True,
                        help_text="WhatsApp number clients should message about payments (e.g. +92 300 1234567).",
                        max_length=32,
                    ),
                ),
                ("contact_phone", models.CharField(blank=True, max_length=32)),
                (
                    "contact_note",
                    models.CharField(
                        blank=True,
                        help_text="Optional extra line shown in emails (e.g. office hours, bank account).",
                        max_length=255,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "tenancy_billing_settings",
                "verbose_name": "Billing & email settings",
                "verbose_name_plural": "Billing & email settings",
            },
        ),
        migrations.CreateModel(
            name="SubscriptionEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("expired", "Subscription expired (grace notice)"),
                            ("suspended", "Access suspended"),
                            ("manual_suspension", "Access suspended (manual)"),
                            ("test", "Test email"),
                        ],
                        max_length=24,
                    ),
                ),
                ("to_email", models.EmailField(max_length=254)),
                (
                    "paid_until",
                    models.DateField(
                        blank=True,
                        null=True,
                        help_text="The billing cycle this email belongs to (dedup key).",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription_emails",
                        to="tenancy.company",
                    ),
                ),
            ],
            options={
                "db_table": "tenancy_subscription_email_log",
                "verbose_name": "Subscription email",
                "verbose_name_plural": "Subscription emails",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="subscriptionemaillog",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind__in", ["expired", "suspended"]), ("paid_until__isnull", False)),
                fields=("company", "kind", "paid_until"),
                name="uniq_subscription_email_per_cycle",
            ),
        ),
    ]
