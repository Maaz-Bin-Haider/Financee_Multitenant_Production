from django.db import migrations


def add_owner_equity_permission(apps, schema_editor):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    content_type, _ = ContentType.objects.get_or_create(app_label='auth', model='user')

    permissions = [
        ('can_manage_owner_equity', 'Can manage owner equity'),
    ]

    for codename, name in permissions:
        Permission.objects.get_or_create(
            codename=codename,
            name=name,
            content_type=content_type,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0016_add_set_opening_permission'),
    ]

    operations = [
        migrations.RunPython(add_owner_equity_permission),
    ]
