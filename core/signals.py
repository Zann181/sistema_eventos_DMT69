from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Group


@receiver(post_migrate)
def crear_grupos_permisos(sender, **kwargs):
    """Crear grupos de permisos automáticamente después de migrar"""
    if sender.name == "core":
        # Crear grupos de roles
        grupos = ["Personal de Entrada", "Personal de Barra", "Administrador"]

        for grupo_nombre in grupos:
            Group.objects.get_or_create(name=grupo_nombre)
            print(f"Grupo creado: {grupo_nombre}")
