import uuid

from django.conf import settings
from django.db import models

from ticketing.application import generate_attendee_qr


class Category(models.Model):
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)
    included_consumptions = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="attendees_category_branch_name_uniq"),
        ]
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"

    def __str__(self):
        return f"{self.branch.name} - {self.name}"


class Attendee(models.Model):
    ORIGIN_MANUAL = "manual"
    ORIGIN_EVENT_DAY = "event_day"
    ORIGIN_CHOICES = [
        (ORIGIN_MANUAL, "Manual"),
        (ORIGIN_EVENT_DAY, "Dia del evento"),
    ]

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="attendees")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="attendees")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="attendees")
    name = models.CharField(max_length=120)
    cc = models.CharField(max_length=32, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    qr_code = models.CharField(max_length=120, unique=True, blank=True)
    qr_image = models.ImageField(upload_to="tickets/qr/", blank=True)
    has_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_in_attendees",
    )
    included_balance = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_attendees_v2",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "cc"], name="attendees_attendee_event_cc_uniq"),
        ]
        verbose_name = "Asistente"
        verbose_name_plural = "Asistentes"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        if not self.qr_code:
            token = uuid.uuid4().hex[:10].upper()
            self.qr_code = f"{self.branch.code_prefix}-{self.event.qr_prefix}-{token}"
        if creating and not self.included_balance:
            self.included_balance = self.category.included_consumptions
        super().save(*args, **kwargs)
        if not self.qr_image:
            generate_attendee_qr(self)

    def __str__(self):
        return f"{self.name} - {self.event.name}"
