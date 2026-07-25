from django.db import migrations


PERMISSIONS = [
    ("view_warehouse", "Can view quantity warehouses"),
    ("create_warehouse", "Can create quantity warehouses"),
    ("update_warehouse", "Can update quantity warehouses"),
    ("delete_warehouse", "Can delete unreferenced quantity warehouses"),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="auth", model="user"
    )
    for codename, name in PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0021_add_opening_stock_permissions"),
    ]

    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
