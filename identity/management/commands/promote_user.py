from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from identity.application import GLOBAL_ADMIN_GROUP


class Command(BaseCommand):
    help = "Promueve un usuario existente a superusuario y Administrador Global."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Nombre de usuario a promover.")

    def handle(self, *args, **options):
        username = options["username"].strip()
        User = get_user_model()

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"No existe un usuario con username '{username}'.") from exc

        updated_fields = []
        if not user.is_active:
            user.is_active = True
            updated_fields.append("is_active")
        if not user.is_staff:
            user.is_staff = True
            updated_fields.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            updated_fields.append("is_superuser")
        if updated_fields:
            user.save(update_fields=updated_fields)

        global_admin_group, _ = Group.objects.get_or_create(name=GLOBAL_ADMIN_GROUP)
        global_admin_group.user_set.add(user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Usuario '{username}' promovido. "
                f"is_active={user.is_active}, is_staff={user.is_staff}, "
                f"is_superuser={user.is_superuser}, grupo='{GLOBAL_ADMIN_GROUP}'."
            )
        )
