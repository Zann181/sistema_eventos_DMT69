from django.contrib import admin

from branches.models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "code_prefix", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug", "contact_email"]

