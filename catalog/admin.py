from django.contrib import admin

from catalog.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "price", "is_active"]
    list_filter = ["branch", "is_active"]
    search_fields = ["name", "description"]
