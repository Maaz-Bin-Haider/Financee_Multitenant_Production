from django.db import migrations


PERMISSIONS = [
    ("view_quantity_audit", "Can view quantity audit events"),
    ("manage_quantity_attachments", "Can manage quantity document attachments"),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="auth", model="user"
    )
    for codename, name in PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename, name=name, content_type=content_type
        )


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0024_add_quantity_count_adjustment_permissions"),
    ]
    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
