from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Sistema de Eventos'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import core.signals