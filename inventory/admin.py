from django.contrib import admin

from inventory.models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["product", "branch", "movement_type", "quantity", "stock_before", "stock_after", "created_at"]
    list_filter = ["branch", "movement_type"]
    search_fields = ["product__name", "note"]

