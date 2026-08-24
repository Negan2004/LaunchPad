from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Importing the module registers its @receiver handlers.
        from . import signals  # noqa: F401
