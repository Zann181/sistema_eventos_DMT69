from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from identity.application import GLOBAL_ADMIN_GROUP


@receiver(post_migrate)
def ensure_global_admin_group(sender, **kwargs):
    if sender.name != "identity":
        return
    Group.objects.get_or_create(name=GLOBAL_ADMIN_GROUP)
