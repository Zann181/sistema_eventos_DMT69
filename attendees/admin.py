from django.contrib import admin

from attendees.models import Attendee, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "price", "included_consumptions", "is_active"]
    list_filter = ["branch", "is_active"]
    search_fields = ["name", "branch__name"]


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "event", "cc", "has_checked_in", "included_balance", "created_at"]
    list_filter = ["branch", "event", "has_checked_in"]
    search_fields = ["name", "cc", "email"]
