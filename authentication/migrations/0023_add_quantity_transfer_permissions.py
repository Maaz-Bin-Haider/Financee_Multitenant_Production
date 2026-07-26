from django.db import migrations


PERMISSIONS = [
    ("view_warehouse_transfer", "Can view quantity warehouse transfers"),
    ("create_warehouse_transfer", "Can create quantity warehouse transfers"),
    ("update_warehouse_transfer", "Can update quantity warehouse transfers"),
    ("delete_warehouse_transfer", "Can reverse quantity warehouse transfers"),
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
        ("authentication", "0022_add_quantity_warehouse_permissions"),
    ]
    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
