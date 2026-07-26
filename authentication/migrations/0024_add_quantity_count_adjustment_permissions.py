from django.db import migrations


PERMISSIONS = [
    ("view_physical_count", "Can view quantity physical counts"),
    ("create_physical_count", "Can create quantity physical counts"),
    ("approve_inventory_adjustment", "Can approve and post inventory adjustments"),
    ("reverse_inventory_adjustment", "Can reverse posted inventory adjustments"),
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
        ("authentication", "0023_add_quantity_transfer_permissions"),
    ]
    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
