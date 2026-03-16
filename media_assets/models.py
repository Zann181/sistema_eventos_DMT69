from django.db import models


class MediaAsset(models.Model):
    KIND_CHOICES = [
        ("branch_logo", "Logo de sucursal"),
        ("event_logo", "Logo de evento"),
        ("event_qr_logo", "Logo de QR del evento"),
        ("event_flyer", "Flyer de evento"),
        ("product_image", "Imagen de producto"),
        ("attendee_qr", "QR de asistente"),
    ]

    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    file = models.FileField(upload_to="assets/")
    checksum = models.CharField(max_length=64)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["content_type", "object_id", "kind"], name="media_assets_owner_kind_uniq"),
        ]
        verbose_name = "Activo multimedia"
        verbose_name_plural = "Activos multimedia"

    def __str__(self):
        return f"{self.kind} - {self.file.name}"
