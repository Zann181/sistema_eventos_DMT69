from django import forms
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import Event
from shared_ui.validators import validate_image_upload, validate_png_upload


DEFAULT_EMAIL_BODY = (
    "Tu registro para {event_name} fue confirmado.\n\n"
    "Fecha: {event_date}\n"
    "Categoria: {category_name}\n"
    "QR: {qr_code}\n\n"
    "Adjuntamos tu codigo QR para el ingreso."
)


class EventForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    ends_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["starts_at"].label = "Fecha y hora del evento"
        self.fields["ends_at"].widget = forms.HiddenInput()
        self.fields["ends_at"].required = False
        self.fields["status"].widget = forms.HiddenInput()
        self.fields["status"].required = False

        if self.instance.pk:
            self.initial["starts_at"] = self._format_datetime_local(self.instance.starts_at)
            self.initial["ends_at"] = self._format_datetime_local(self.instance.ends_at or self.instance.starts_at)
            self.fields["ends_at"].initial = self.instance.ends_at or self.instance.starts_at
            self.fields["status"].initial = self.instance.status or Event.STATUS_ACTIVE
        else:
            self.fields["ends_at"].initial = self.initial.get("starts_at")
            self.fields["status"].initial = Event.STATUS_ACTIVE
            self.initial["email_body"] = DEFAULT_EMAIL_BODY
            self.fields["email_body"].initial = DEFAULT_EMAIL_BODY

    @staticmethod
    def _format_datetime_local(value):
        if not value:
            return ""
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if not parsed:
                return value
            value = parsed
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["ends_at"] = cleaned_data.get("ends_at") or cleaned_data.get("starts_at")
        cleaned_data["status"] = cleaned_data.get("status") or Event.STATUS_ACTIVE
        return cleaned_data

    def clean_logo(self):
        return validate_png_upload(self.cleaned_data.get("logo"), field_label="logo del evento")

    def clean_flyer(self):
        return validate_image_upload(self.cleaned_data.get("flyer"), field_label="flyer del evento")

    class Meta:
        model = Event
        fields = [
            "name",
            "slug",
            "description",
            "starts_at",
            "ends_at",
            "status",
            "qr_prefix",
            "logo",
            "flyer",
            "qr_fill_color",
            "qr_background_color",
            "qr_logo_background_color",
            "qr_logo_scale",
            "access_policy",
            "email_subject",
            "email_preheader",
            "email_heading",
            "email_intro",
            "email_message_title",
            "email_body",
            "email_warning_title",
            "email_warning_text",
            "email_details_title",
            "email_date_text",
            "email_time_text",
            "venue_name",
            "maps_url",
            "maps_label",
            "dress_code",
            "email_qr_title",
            "email_qr_note",
            "email_footer",
            "email_closing_text",
            "email_team_signature",
            "email_legal_note",
            "email_background_color",
            "email_card_color",
            "email_header_background_color",
            "email_text_color",
            "email_muted_text_color",
            "email_accent_color",
            "email_border_color",
            "email_section_background_color",
            "email_warning_background_color",
        ]

        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "access_policy": forms.Textarea(attrs={"rows": 3}),
            "logo": forms.FileInput(attrs={"accept": ".png,image/png"}),
            "flyer": forms.FileInput(attrs={"accept": "image/*"}),
            "email_subject": forms.TextInput(
                attrs={
                    "data-email-preview": "subject",
                    "placeholder": "Tu acceso esta listo: {nombre_evento}",
                }
            ),
            "email_preheader": forms.TextInput(
                attrs={
                    "data-email-preview": "preheader",
                    "placeholder": "Popayan se viste de negro - Todos de negro - Closing 2025",
                }
            ),
            "email_heading": forms.TextInput(
                attrs={
                    "data-email-preview": "heading",
                    "placeholder": "Hola {nombre_asistente}",
                }
            ),
            "email_intro": forms.Textarea(
                attrs={
                    "rows": 3,
                    "data-email-preview": "intro",
                    "placeholder": "Texto de bienvenida debajo del titulo.",
                }
            ),
            "email_message_title": forms.TextInput(
                attrs={
                    "data-email-preview": "messageTitle",
                    "placeholder": "Mensaje del evento",
                }
            ),
            "email_body": forms.Textarea(
                attrs={
                    "rows": 8,
                    "data-email-preview": "body",
                    "placeholder": "Contenido principal del correo",
                }
            ),
            "email_warning_title": forms.TextInput(
                attrs={
                    "data-email-preview": "warningTitle",
                    "placeholder": "Importante",
                }
            ),
            "email_warning_text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "data-email-preview": "warningText",
                    "placeholder": "Texto del bloque importante o early.",
                }
            ),
            "email_details_title": forms.TextInput(
                attrs={
                    "data-email-preview": "detailsTitle",
                    "placeholder": "Detalles",
                }
            ),
            "email_date_text": forms.TextInput(
                attrs={
                    "data-email-preview": "dateText",
                    "placeholder": "Viernes 19 de Diciembre de 2025 (DIC 19)",
                }
            ),
            "email_time_text": forms.TextInput(
                attrs={
                    "data-email-preview": "timeText",
                    "placeholder": "9:00 PM",
                }
            ),
            "venue_name": forms.TextInput(
                attrs={
                    "data-email-preview": "venue",
                    "placeholder": "Terrazas Campestres - K3 Via Totoro",
                }
            ),
            "maps_url": forms.URLInput(
                attrs={
                    "data-email-preview": "mapsUrl",
                    "placeholder": "https://maps.google.com/...",
                }
            ),
            "maps_label": forms.TextInput(
                attrs={
                    "data-email-preview": "mapsLabel",
                    "placeholder": "Abrir en Google Maps",
                }
            ),
            "dress_code": forms.TextInput(
                attrs={
                    "data-email-preview": "dressCode",
                    "placeholder": "Todos de negro",
                }
            ),
            "qr_fill_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "qrFill"}),
            "qr_background_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "qrBackground"}),
            "qr_logo_background_color": forms.TextInput(
                attrs={"type": "color", "data-email-preview": "qrLogoBackground"}
            ),
            "qr_logo_scale": forms.NumberInput(
                attrs={
                    "min": 2,
                    "max": 6,
                    "step": 1,
                    "data-email-preview": "qrLogoScale",
                }
            ),
            "email_qr_title": forms.TextInput(
                attrs={
                    "data-email-preview": "qrTitle",
                    "placeholder": "Tu codigo QR esta adjunto a este correo",
                }
            ),
            "email_qr_note": forms.TextInput(
                attrs={
                    "data-email-preview": "qrNote",
                    "placeholder": "Presentalo junto a tu cedula en la entrada.",
                }
            ),
            "email_footer": forms.TextInput(
                attrs={
                    "data-email-preview": "footer",
                    "placeholder": "Texto final o instruccion",
                }
            ),
            "email_closing_text": forms.TextInput(
                attrs={
                    "data-email-preview": "closingText",
                    "placeholder": "Nos vemos pronto.",
                }
            ),
            "email_team_signature": forms.TextInput(
                attrs={
                    "data-email-preview": "teamSignature",
                    "placeholder": "Equipo {nombre_evento}",
                }
            ),
            "email_legal_note": forms.TextInput(
                attrs={
                    "data-email-preview": "legalNote",
                    "placeholder": "Correo automatico - conserva tu QR hasta el dia del evento.",
                }
            ),
            "email_background_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "background"}),
            "email_card_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "card"}),
            "email_header_background_color": forms.TextInput(
                attrs={"type": "color", "data-email-preview": "headerBackground"}
            ),
            "email_text_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "text"}),
            "email_muted_text_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "muted"}),
            "email_accent_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "accent"}),
            "email_border_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "border"}),
            "email_section_background_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "section"}),
            "email_warning_background_color": forms.TextInput(attrs={"type": "color", "data-email-preview": "warning"}),
        }

        help_texts = {
            "email_subject": (
                "Puedes usar {nombre_asistente}, {nombre_evento}, {nombre_sucursal}, "
                "{fecha_evento}, {hora_evento}, {nombre_categoria}, {cedula_asistente}, "
                "{precio_categoria}, {codigo_qr}."
            ),
            "email_heading": "Titulo principal que vera el cliente en el correo.",
            "email_body": "Mensaje principal del evento. Soporta las mismas variables dinamicas.",
            "email_warning_text": "Usalo para early, advertencias o condiciones especiales.",
            "email_date_text": "Texto libre para la fecha. Puede usar {fecha_evento}.",
            "email_time_text": "Texto libre para la hora. Puede usar {hora_evento}.",
            "email_footer": "Mensaje corto al final del correo.",
            "logo": "Solo PNG. Este logo se usa en el evento y tambien en el QR.",
            "qr_logo_scale": "4 es el tamano recomendado: ocupa aprox. una cuarta parte del QR.",
        }

        labels = {
            "name": "Nombre del evento",
            "slug": "Identificador URL",
            "description": "Descripcion",
            "starts_at": "Fecha y hora del evento",
            "ends_at": "Fecha y hora de cierre",
            "status": "Estado",
            "qr_prefix": "Prefijo QR",
            "logo": "Logo principal",
            "flyer": "Flyer",
            "qr_fill_color": "Color del QR",
            "qr_background_color": "Color de fondo del QR",
            "qr_logo_background_color": "Color del circulo del logo",
            "qr_logo_scale": "Tamano del logo",
            "access_policy": "Politica de acceso",
            "email_subject": "Asunto del correo",
            "email_preheader": "Texto corto del encabezado",
            "email_heading": "Titulo del correo",
            "email_intro": "Introduccion del correo",
            "email_message_title": "Titulo del mensaje del evento",
            "email_body": "Contenido del correo",
            "email_warning_title": "Titulo del bloque importante",
            "email_warning_text": "Texto del bloque importante",
            "email_details_title": "Titulo de detalles",
            "email_date_text": "Texto de la fecha",
            "email_time_text": "Texto de la hora",
            "venue_name": "Lugar",
            "maps_url": "URL de Google Maps",
            "maps_label": "Texto del enlace de ubicacion",
            "dress_code": "Dress code",
            "email_qr_title": "Titulo del bloque QR",
            "email_qr_note": "Nota del bloque QR",
            "email_footer": "Pie del correo",
            "email_closing_text": "Texto de cierre",
            "email_team_signature": "Firma del equipo",
            "email_legal_note": "Nota legal o automatica",
            "email_background_color": "Color de fondo",
            "email_card_color": "Color de tarjeta",
            "email_header_background_color": "Color del encabezado",
            "email_text_color": "Color de texto",
            "email_muted_text_color": "Color de texto secundario",
            "email_accent_color": "Color de acento",
            "email_border_color": "Color de borde",
            "email_section_background_color": "Color de cajas",
            "email_warning_background_color": "Color de caja importante",
        }
