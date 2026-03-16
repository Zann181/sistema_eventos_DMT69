from django.conf import settings
from django.db import models
import uuid
from decimal import Decimal


class EventProduct(models.Model):
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="event_products")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="product_settings")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="event_settings")
    is_enabled = models.BooleanField(default=False)
    event_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="event_product_updates")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name"]
        unique_together = [("event", "product")]
        verbose_name = "Producto habilitado por evento"
        verbose_name_plural = "Productos habilitados por evento"

    def normalized_event_price(self):
        if self.event_price is None:
            return None
        price = Decimal(self.event_price)
        base_price = Decimal(self.product.price or 0)
        if base_price <= 0:
            return price
        while price >= (base_price * Decimal("10")) and price == price.to_integral_value():
            price = price / Decimal("10")
        return price

    @property
    def effective_price(self):
        normalized = self.normalized_event_price()
        return normalized if normalized is not None else self.product.price

    def __str__(self):
        return f"{self.event.name} - {self.product.name}"


class BarSale(models.Model):
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="sales")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="sales")
    sale_group = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    attendee = models.ForeignKey("attendees.Attendee", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="sales")
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    used_included_consumption = models.BooleanField(default=False)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sales_v2")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Venta de barra"
        verbose_name_plural = "Ventas de barra"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


class CashMovement(models.Model):
    MODULE_ENTRANCE = "entrada"
    MODULE_BAR = "barra"
    MODULE_CHOICES = [
        (MODULE_ENTRANCE, "Entrada"),
        (MODULE_BAR, "Barra"),
    ]

    TYPE_EVENT_DAY = "evento_dia"
    TYPE_EXPENSE = "gasto"
    TYPE_CASH_DROP = "vaciar_caja"
    TYPE_CHOICES = [
        (TYPE_EVENT_DAY, "Dia de evento"),
        (TYPE_EXPENSE, "Gasto"),
        (TYPE_CASH_DROP, "Vaciar caja"),
    ]

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="cash_movements")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="cash_movements")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cash_movements")
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    attendee_quantity = models.PositiveIntegerField(default=0)
    unit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Movimiento de caja"
        verbose_name_plural = "Movimientos de caja"

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.get_module_display()} - {self.total_amount}"


class CashMovementPayment(models.Model):
    METHOD_CASH = "efectivo"
    METHOD_TRANSFER = "transferencia"
    METHOD_QR = "qr"
    METHOD_CARD = "tarjeta"
    METHOD_CHOICES = [
        (METHOD_CASH, "Efectivo"),
        (METHOD_TRANSFER, "Transferencia"),
        (METHOD_QR, "QR"),
        (METHOD_CARD, "Tarjeta"),
    ]

    movement = models.ForeignKey(CashMovement, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    transfer_proof = models.ImageField(upload_to="cash/proofs/", blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Pago de movimiento"
        verbose_name_plural = "Pagos de movimientos"

    def __str__(self):
        return f"{self.get_method_display()} - {self.amount}"


class BarSalePayment(models.Model):
    sale = models.ForeignKey(BarSale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=20, choices=CashMovementPayment.METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    transfer_proof = models.ImageField(upload_to="sales/proofs/", blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Pago de venta de barra"
        verbose_name_plural = "Pagos de ventas de barra"

    def __str__(self):
        return f"{self.sale_id} - {self.get_method_display()} - {self.amount}"
