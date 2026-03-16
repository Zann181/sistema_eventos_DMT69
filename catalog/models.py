from django.conf import settings
from django.db import models


class Product(models.Model):
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="catalog/products/", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        from media_assets.application import persist_image_asset

        persist_image_asset(self, "image", "product_image")

    def __str__(self):
        return f"{self.branch.name} - {self.name}"
