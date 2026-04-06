from django.db import migrations
import django.db.models.fields


class Migration(migrations.Migration):
    """
    No-op migration. Superadmin access is handled via Django's built-in
    is_superuser flag rather than a dedicated role choice.
    """

    dependencies = [
        ('users', '0027_customuser_is_technician'),
    ]

    operations = []
