from django.contrib import admin

from events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "status", "starts_at", "ends_at"]
    list_filter = ["status", "branch"]
    search_fields = ["name", "slug"]

