"""
tenancy.admin
=============
Register Company, Membership, and SubscriptionPayment on the **custom**
Financee admin site (``financee.admin_site.financee_admin_site``) so the whole
multi-tenant setup — including monthly subscription control — is driven from
the existing admin panel (business rule #18).

* Creating a Company here triggers schema provisioning (via the post_save
  signal) — no shell command required.
* ``schema_name`` and ``created_at`` are read-only: the schema name is
  machine-generated and must never be edited, or the registry would point at
  the wrong physical schema.
* Membership uses the OneToOne on ``user`` to enforce one-company-per-user; the
  admin surfaces a clear error if you try to add a second membership for a user.

Subscription workflow (payments arrive outside the system, e.g. bank transfer):

* Each company carries ``paid_until`` + ``grace_days``; when the grace window
  passes, every user of that company is blocked automatically by the tenant
  middleware. ``is_suspended`` is the manual kill switch.
* Recording a **Subscription payment** (inline on the company, or from its own
  changelist) extends ``paid_until`` by the months covered and lifts a manual
  suspension — so "client paid" is a single admin action.
* Payments are an immutable audit log: editing or deleting one never shrinks
  ``paid_until``.
"""
from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from financee.admin_site import financee_admin_site

from .models import (
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_BLOCKED,
    SUBSCRIPTION_EXPIRING,
    SUBSCRIPTION_GRACE,
    SUBSCRIPTION_SUSPENDED,
    SUBSCRIPTION_UNRESTRICTED,
    BillingSettings,
    Company,
    Membership,
    SubscriptionEmailLog,
    SubscriptionPayment,
)
from .subscription_emails import send_manual_suspension_email, send_test_email


# state -> (label template, pill CSS class). Muted palette per admin UI notes.
SUBSCRIPTION_BADGES = {
    SUBSCRIPTION_UNRESTRICTED: ("Not enforced", "pill-user"),
    SUBSCRIPTION_ACTIVE: ("Active", "pill-active"),
    SUBSCRIPTION_EXPIRING: ("Expires {date}", "pill-warn"),
    SUBSCRIPTION_GRACE: ("Grace until {date}", "pill-grace"),
    SUBSCRIPTION_BLOCKED: ("Blocked — unpaid", "pill-inactive"),
    SUBSCRIPTION_SUSPENDED: ("Suspended", "pill-inactive"),
}


def subscription_badge_html(company):
    state = company.subscription_state()
    label, css = SUBSCRIPTION_BADGES[state]
    if "{date}" in label:
        date_value = company.paid_until if state == SUBSCRIPTION_EXPIRING else company.grace_until
        label = label.format(date=date_value.strftime("%d %b %Y"))
    return format_html('<span class="fin-pill {}">{}</span>', css, label)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ["user"]
    verbose_name = "Member"
    verbose_name_plural = "Members"


class SubscriptionPaymentInline(admin.TabularInline):
    model = SubscriptionPayment
    extra = 0
    fields = ("date_received", "amount", "months_covered", "note", "paid_until_after", "created_by")
    readonly_fields = ("paid_until_after", "created_by")
    ordering = ("-date_received", "-id")
    verbose_name = "Subscription payment"
    verbose_name_plural = "Subscription payments (adding one extends Paid until and lifts a suspension)"

    def has_change_permission(self, request, obj=None):
        # Payments are an audit log; corrections go through Paid until directly.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "schema_name",
        "is_active",
        "subscription_badge",
        "paid_until",
        "member_count",
        "created_at",
    )
    list_filter = ("is_active", "is_suspended")
    search_fields = ("name", "schema_name")
    readonly_fields = ("schema_name", "created_at", "subscription_badge")
    inlines = [SubscriptionPaymentInline, MembershipInline]
    actions = ["suspend_companies", "unsuspend_companies"]

    fieldsets = (
        (None, {"fields": ("name", "schema_name", "is_active", "created_at")}),
        (
            "Subscription",
            {
                "fields": ("subscription_badge", "contact_email", "paid_until", "grace_days", "warn_days_before", "is_suspended"),
                "description": (
                    "Users of this company are blocked automatically once "
                    "<b>Paid until</b> + <b>Grace days</b> passes, or immediately when "
                    "<b>Suspended</b> is ticked. Leave <b>Paid until</b> empty to disable "
                    "subscription enforcement. Record a payment below to extend access. "
                    "Expiry/suspension emails go to <b>Contact email</b> (sender account "
                    "and contact details live in Billing &amp; email settings)."
                ),
            },
        ),
    )

    @admin.display(description="Subscription")
    def subscription_badge(self, obj):
        return subscription_badge_html(obj)

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.memberships.count()

    @admin.action(description="Suspend selected companies (block access now)")
    def suspend_companies(self, request, queryset):
        newly_suspended = list(queryset.filter(is_suspended=False))
        updated = queryset.update(is_suspended=True)
        self.message_user(request, f"{updated} company(ies) suspended — their users are blocked immediately.")
        for company in newly_suspended:
            company.is_suspended = True
            self._notify_manual_suspension(request, company)

    @admin.action(description="Lift suspension for selected companies")
    def unsuspend_companies(self, request, queryset):
        updated = queryset.update(is_suspended=False)
        self.message_user(
            request,
            f"Suspension lifted for {updated} company(ies). Companies past their "
            "paid-until grace window remain blocked until a payment is recorded.",
        )

    def save_model(self, request, obj, form, change):
        was_suspended = False
        if change:
            was_suspended = Company.objects.filter(pk=obj.pk, is_suspended=True).exists()
        super().save_model(request, obj, form, change)
        if change and obj.is_suspended and not was_suspended:
            self._notify_manual_suspension(request, obj)

    def _notify_manual_suspension(self, request, company):
        ok, detail = send_manual_suspension_email(company)
        if ok:
            self.message_user(
                request, f"Suspension email sent to {company.contact_email} ({company.name})."
            )
        else:
            self.message_user(
                request,
                f"No suspension email for {company.name}: {detail}.",
                level=messages.WARNING,
            )

    def save_formset(self, request, form, formset, change):
        # Stamp who recorded each new subscription payment.
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if isinstance(instance, SubscriptionPayment) and instance.pk is None:
                instance.created_by = request.user
            instance.save()
        formset.save_m2m()


class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "created_at")
    list_filter = ("company",)
    search_fields = ("user__username", "user__email", "company__name")
    autocomplete_fields = ["user", "company"]


class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "amount",
        "date_received",
        "months_covered",
        "paid_until_after",
        "note",
        "created_by",
        "created_at",
    )
    list_filter = ("company",)
    date_hierarchy = "date_received"
    search_fields = ("company__name", "note")
    autocomplete_fields = ["company"]
    readonly_fields = ("paid_until_after", "created_by", "created_at")

    def get_readonly_fields(self, request, obj=None):
        # Immutable once recorded: it already extended the company's paid_until.
        if obj is not None:
            return [f.name for f in self.model._meta.fields if f.name != "id"]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class BillingSettingsForm(forms.ModelForm):
    class Meta:
        model = BillingSettings
        fields = "__all__"
        widgets = {
            "app_password": forms.PasswordInput(render_value=True),
        }


class BillingSettingsAdmin(admin.ModelAdmin):
    """Singleton: the changelist jumps straight to the one settings form."""

    form = BillingSettingsForm
    readonly_fields = ("updated_at",)

    def get_fieldsets(self, request, obj=None):
        try:
            test_url = reverse("admin:tenancy_billingsettings_test_email")
            test_link = (
                f' <a class="button" href="{test_url}">Send a test email to the sender address</a>'
            )
        except Exception:
            test_link = ""
        return (
            (
                "Sender account (SMTP)",
                {
                    "fields": ("sender_name", "sender_email", "app_password", "smtp_host", "smtp_port", "use_tls", "emails_enabled"),
                    "description": (
                        "Subscription emails are sent from this account. For Gmail, create an "
                        "<b>app password</b> (Google Account &rarr; Security &rarr; 2-Step Verification "
                        "&rarr; App passwords) and paste it here. <b>Save first</b>, then verify with:"
                        + test_link
                    ),
                },
            ),
            (
                "Contact details shown in emails",
                {
                    "fields": ("whatsapp_number", "contact_phone", "contact_note", "updated_at"),
                    "description": (
                        "These appear in every expiry/suspension email so clients can reach "
                        "you easily to arrange payment."
                    ),
                },
            ),
        )

    def has_add_permission(self, request):
        return False  # the row is auto-created; there is only ever one

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_row = BillingSettings.get_solo()
        return redirect(
            reverse("admin:tenancy_billingsettings_change", args=[settings_row.pk])
        )

    def get_urls(self):
        custom = [
            path(
                "send-test-email/",
                self.admin_site.admin_view(self.send_test_email_view),
                name="tenancy_billingsettings_test_email",
            ),
        ]
        return custom + super().get_urls()

    def send_test_email_view(self, request):
        settings_row = BillingSettings.get_solo()
        if not settings_row.sender_email:
            self.message_user(request, "Set and save a sender email first.", level=messages.WARNING)
        else:
            ok, detail = send_test_email(settings_row.sender_email)
            if ok:
                self.message_user(
                    request,
                    f"Test email sent to {settings_row.sender_email} — check the inbox.",
                )
            else:
                self.message_user(request, f"Test email failed: {detail}", level=messages.ERROR)
        return redirect(
            reverse("admin:tenancy_billingsettings_change", args=[settings_row.pk])
        )


class SubscriptionEmailLogAdmin(admin.ModelAdmin):
    """Read-only audit trail of every subscription email."""

    list_display = ("created_at", "company", "kind", "to_email", "paid_until", "status", "short_error")
    list_filter = ("kind", "status", "company")
    search_fields = ("to_email", "company__name", "error")
    date_hierarchy = "created_at"

    @admin.display(description="Error")
    def short_error(self, obj):
        return (obj.error[:80] + "…") if len(obj.error) > 80 else (obj.error or "—")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Sent rows are the dedup guard for their billing cycle; deleting one
        # would allow a duplicate email for that cycle.
        return False


financee_admin_site.register(Company, CompanyAdmin)
financee_admin_site.register(Membership, MembershipAdmin)
financee_admin_site.register(SubscriptionPayment, SubscriptionPaymentAdmin)
financee_admin_site.register(BillingSettings, BillingSettingsAdmin)
financee_admin_site.register(SubscriptionEmailLog, SubscriptionEmailLogAdmin)
