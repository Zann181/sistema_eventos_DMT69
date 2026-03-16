from django.db import models
from django.utils.text import slugify
from django.core.validators import MaxValueValidator, MinValueValidator


class Event(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Borrador"),
        (STATUS_ACTIVE, "Activo"),
        (STATUS_ARCHIVED, "Archivado"),
    ]

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="events")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    qr_prefix = models.CharField(max_length=20, default="EVT")
    logo = models.ImageField(upload_to="events/logos/", blank=True)
    qr_logo = models.ImageField(upload_to="events/qr_logos/", blank=True)
    flyer = models.ImageField(upload_to="events/flyers/", blank=True)
    qr_fill_color = models.CharField(max_length=7, default="#102542")
    qr_background_color = models.CharField(max_length=7, default="#f8f9fa")
    qr_logo_background_color = models.CharField(max_length=7, default="#ffffff")
    qr_logo_scale = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(2), MaxValueValidator(6)],
    )
    access_policy = models.TextField(blank=True)
    email_subject = models.CharField(max_length=180, default="Tu acceso esta listo: {event_name}")
    email_preheader = models.CharField(
        max_length=220,
        default="Popayan se viste de negro - Todos de negro - Closing 2025",
    )
    email_heading = models.CharField(max_length=180, default="Hola {attendee_name}")
    email_intro = models.TextField(
        default="Tu asistencia ha sido confirmada. Abajo tienes la info oficial del evento:"
    )
    email_message_title = models.CharField(max_length=140, default="Mensaje del evento")
    email_body = models.TextField(
        default=(
            "Tu registro para {event_name} fue confirmado.\n\n"
            "Sucursal: {branch_name}\n"
            "Fecha: {event_date}\n"
            "Categoria: {category_name}\n"
            "QR: {qr_code}\n\n"
            "Adjuntamos tu codigo QR para el ingreso."
        )
    )
    email_warning_title = models.CharField(max_length=140, default="Importante")
    email_warning_text = models.TextField(
        default="Ingreso Early hasta las 11:00 PM. Despues de esa hora aplica multa de $25.000."
    )
    email_details_title = models.CharField(max_length=140, default="Detalles")
    email_date_text = models.CharField(max_length=180, default="{fecha_evento}")
    email_time_text = models.CharField(max_length=120, default="{hora_evento}")
    venue_name = models.CharField(max_length=220, default="Terrazas Campestres - K3 Via Totoro")
    maps_url = models.URLField(blank=True)
    maps_label = models.CharField(max_length=120, default="Abrir en Google Maps")
    dress_code = models.CharField(max_length=160, default="Todos de negro")
    email_qr_title = models.CharField(max_length=180, default="Tu codigo QR esta adjunto a este correo")
    email_qr_note = models.CharField(
        max_length=220,
        default="Presentalo junto a tu cedula en la entrada.",
    )
    email_footer = models.CharField(max_length=220, default="Presenta este correo en la entrada del evento.")
    email_closing_text = models.CharField(max_length=220, default="Nos vemos pronto.")
    email_team_signature = models.CharField(max_length=220, default="Equipo {event_name}")
    email_legal_note = models.CharField(
        max_length=220,
        default="Correo automatico - conserva tu QR hasta el dia del evento.",
    )
    email_background_color = models.CharField(max_length=7, default="#f6f2eb")
    email_card_color = models.CharField(max_length=7, default="#ffffff")
    email_header_background_color = models.CharField(max_length=7, default="#111315")
    email_text_color = models.CharField(max_length=7, default="#172121")
    email_muted_text_color = models.CharField(max_length=7, default="#bdbdbd")
    email_accent_color = models.CharField(max_length=7, default="#c44536")
    email_border_color = models.CharField(max_length=7, default="#1f1f22")
    email_section_background_color = models.CharField(max_length=7, default="#18191b")
    email_warning_background_color = models.CharField(max_length=7, default="#2a1c17")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "slug"], name="events_event_branch_slug_uniq"),
        ]
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

        from media_assets.application import field_file_exists, persist_image_asset, restore_field_from_asset

        for field_name, kind in (
            ("logo", "event_logo"),
            ("qr_logo", "event_qr_logo"),
            ("flyer", "event_flyer"),
        ):
            field_file = getattr(self, field_name, None)
            if not field_file or not field_file_exists(field_file):
                field_file = restore_field_from_asset(self, field_name, kind)
            if field_file:
                persist_image_asset(self, field_name, kind)

    def __str__(self):
        return f"{self.branch.name} - {self.name}"
