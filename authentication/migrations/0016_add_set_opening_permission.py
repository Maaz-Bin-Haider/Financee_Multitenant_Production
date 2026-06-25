from django.db import migrations


def add_set_opening_permission(apps, schema_editor):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    content_type, _ = ContentType.objects.get_or_create(app_label='auth', model='user')

    permissions = [
        ('can_set_or_update_opening', 'Can set or update opening'),
    ]

    for codename, name in permissions:
        Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0015_add_dashboard_options_permissions'),
    ]

    operations = [
        migrations.RunPython(add_set_opening_permission),
    ]
