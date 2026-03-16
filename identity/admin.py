from django.contrib import admin

from identity.models import UserBranchMembership


@admin.register(UserBranchMembership)
class UserBranchMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "branch", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active", "branch"]
    search_fields = ["user__username", "branch__name"]

