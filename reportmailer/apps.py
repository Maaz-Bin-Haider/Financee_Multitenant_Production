from django.apps import AppConfig
from django.db.models.signals import post_migrate


def seed_report_permissions(sender, using="default", **kwargs):
    # Match draft's post_migrate seeding; do not change audited migration history
    # or automatically grant access to an existing company/user.
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    content_type, _ = ContentType.objects.db_manager(using).get_or_create(app_label="auth", model="user")
    Permission.objects.db_manager(using).get_or_create(
        codename="send_reports", content_type=content_type,
        defaults={"name": "Can configure and send company report emails"})


class ReportMailerConfig(AppConfig):
    name = "reportmailer"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(seed_report_permissions, sender=self,
                             dispatch_uid="reportmailer.seed_permissions")
