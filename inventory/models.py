from django.conf import settings
from django.db import models


class StockMovement(models.Model):
    TYPE_ENTRY = "entrada"
    TYPE_EXIT = "salida"
    TYPE_ADJUSTMENT = "ajuste"
    TYPE_SALE = "venta"
    TYPE_CHOICES = [
        (TYPE_ENTRY, "Entrada"),
        (TYPE_EXIT, "Salida"),
        (TYPE_ADJUSTMENT, "Ajuste"),
        (TYPE_SALE, "Venta"),
    ]

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="stock_movements")
    event = models.ForeignKey("events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    quantity = models.IntegerField()
    stock_before = models.IntegerField()
    stock_after = models.IntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Movimiento de stock"
        verbose_name_plural = "Movimientos de stock"

    def __str__(self):
        return f"{self.product.name} - {self.get_movement_type_display()} ({self.quantity})"

