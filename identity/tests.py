from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from identity.application import GLOBAL_ADMIN_GROUP


class PromoteUserCommandTests(TestCase):
    def test_promote_user_sets_superuser_flags_and_global_admin_group(self):
        user = get_user_model().objects.create_user(
            username="motaz-admin",
            password="12345678@",
            is_active=False,
        )

        output = StringIO()
        call_command("promote_user", "motaz-admin", stdout=output)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(
            Group.objects.get(name=GLOBAL_ADMIN_GROUP).user_set.filter(pk=user.pk).exists()
        )
        self.assertIn("Usuario 'motaz-admin' promovido.", output.getvalue())
