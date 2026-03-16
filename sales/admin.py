from django.contrib import admin

from sales.models import BarSale


@admin.register(BarSale)
class BarSaleAdmin(admin.ModelAdmin):
    list_display = ["product", "branch", "event", "quantity", "total", "used_included_consumption", "created_at"]
    list_filter = ["branch", "event", "used_included_consumption"]
    search_fields = ["product__name", "attendee__name"]

