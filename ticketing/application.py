import base64
import email.policy
import re
from email.message import EmailMessage as PythonEmailMessage
from decimal import Decimal
from html import escape
from io import BytesIO
from types import SimpleNamespace

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware

from media_assets.application import persist_image_asset, resolve_field_file


class RelatedEmailMultiAlternatives(EmailMultiAlternatives):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inline_images = []

    def attach_inline_image(self, content, cid, filename, mimetype="image/png"):
        self.inline_images.append(
            {
                "content": content,
                "cid": cid,
                "filename": filename,
                "mimetype": mimetype,
            }
        )

    def message(self, *, policy=email.policy.default):
        encoding = self.encoding or settings.DEFAULT_CHARSET
        message = PythonEmailMessage(policy=policy)
        message["Subject"] = self.subject
        message["From"] = self.extra_headers.get("From", self.from_email)
        if self.to:
            message["To"] = ", ".join(str(value) for value in self.to)
        if self.cc:
            message["Cc"] = ", ".join(str(value) for value in self.cc)
        if self.reply_to:
            message["Reply-To"] = ", ".join(str(value) for value in self.reply_to)
        for key, value in self.extra_headers.items():
            if key.lower() not in {"from", "to", "cc", "reply-to"}:
                message[key] = value

        message.set_content(self.body or "", subtype=self.content_subtype, charset=encoding)

        html_part = None
        for alternative in self.alternatives:
            maintype, subtype = alternative.mimetype.split("/", 1)
            if maintype == "text":
                content = alternative.content.decode() if isinstance(alternative.content, bytes) else alternative.content
                message.add_alternative(content, subtype=subtype, charset=encoding)
                if subtype == "html":
                    html_part = message.get_body(preferencelist=("html",))
            else:
                content = alternative.content if isinstance(alternative.content, bytes) else str(alternative.content).encode(encoding)
                message.add_alternative(content, maintype=maintype, subtype=subtype)

        if html_part:
            for inline in self.inline_images:
                maintype, subtype = inline["mimetype"].split("/", 1)
                html_part.add_related(
                    inline["content"],
                    maintype=maintype,
                    subtype=subtype,
                    cid=f"<{inline['cid']}>",
                    disposition="inline",
                )

        for attachment in self.attachments:
            self._add_attachment(message, *attachment)

        return message


def _get_qr_logo_source(event, branch):
    for field_file in [
        resolve_field_file(event, "logo", "event_logo"),
        resolve_field_file(branch, "logo", "branch_logo"),
    ]:
        if not field_file:
            continue
        try:
            field_file.open("rb")
            image = Image.open(field_file).convert("RGBA")
            image.load()
            field_file.close()
            return image
        except (FileNotFoundError, ValueError):
            continue
    return None


def _build_qr_image(code, event, branch):
    # Give the reader more quiet zone and module size before adding the centered logo.
    qr = qrcode.QRCode(box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(code)
    qr.make(fit=True)
    image = qr.make_image(
        fill_color=getattr(event, "qr_fill_color", "#102542"),
        back_color=getattr(event, "qr_background_color", "#f8f9fa"),
    ).convert("RGBA")

    logo = _get_qr_logo_source(event, branch)
    if not logo:
        return image

    logo_scale = max(int(getattr(event, "qr_logo_scale", 4) or 4), 2)
    overlay_size = max(image.width // max(logo_scale, 2), 48)
    overlay_size = min(overlay_size, max(image.width // 4, 48))
    badge = Image.new("RGBA", (overlay_size, overlay_size), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.ellipse(
        (0, 0, overlay_size - 1, overlay_size - 1),
        fill=getattr(event, "qr_logo_background_color", "#ffffff"),
        outline=(255, 255, 255, 235),
        width=max(2, overlay_size // 18),
    )

    inner_size = max(int(overlay_size * 0.68), 28)
    logo = ImageOps.contain(logo, (inner_size, inner_size), method=Image.Resampling.LANCZOS)
    badge.paste(
        logo,
        ((overlay_size - logo.size[0]) // 2, (overlay_size - logo.size[1]) // 2),
        mask=logo.split()[-1] if "A" in logo.getbands() else None,
    )

    position = ((image.width - overlay_size) // 2, (image.height - overlay_size) // 2)
    image.alpha_composite(badge, dest=position)
    return image


def build_qr_png_bytes(code, event, branch):
    image = _build_qr_image(code, event, branch).convert("RGB")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_qr_preview_data_uri(code, event, branch):
    png_bytes = build_qr_png_bytes(code, event, branch)
    return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"


def build_qr_preview_event(source_event, branch, files=None, data=None):
    files = files or {}
    data = data or {}
    return SimpleNamespace(
        qr_fill_color=data.get("qr_fill_color") or getattr(source_event, "qr_fill_color", "#102542"),
        qr_background_color=data.get("qr_background_color") or getattr(source_event, "qr_background_color", "#f8f9fa"),
        qr_logo_background_color=data.get("qr_logo_background_color")
        or getattr(source_event, "qr_logo_background_color", "#ffffff"),
        qr_logo_scale=data.get("qr_logo_scale") or getattr(source_event, "qr_logo_scale", 4),
        logo=files.get("logo") or resolve_field_file(source_event, "logo", "event_logo"),
    )


def generate_attendee_qr(attendee):
    output = BytesIO()
    _build_qr_image(attendee.qr_code, attendee.event, attendee.branch).convert("RGB").save(
        output,
        format="WEBP",
        quality=88,
        method=6,
    )
    attendee.qr_image.save(f"{attendee.qr_code}.webp", ContentFile(output.getvalue()), save=False)
    attendee.__class__.objects.filter(pk=attendee.pk).update(qr_image=attendee.qr_image.name)
    persist_image_asset(attendee, "qr_image", "attendee_qr")


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _format_price(value):
    if value in (None, ""):
        return ""
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return str(int(normalized))
        return format(normalized, "f")
    return str(value)


def _multiline_html(value):
    return escape(value or "").replace("\n", "<br>")


def _remove_branch_lines(value):
    lines = []
    for raw_line in str(value or "").splitlines():
        normalized = raw_line.strip().lower()
        if normalized.startswith("sucursal:") or normalized.startswith("branch:"):
            continue
        lines.append(raw_line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _render_email_body_text(value, qr_code):
    text = str(value or "")
    replacements = [
        (f"QR: {qr_code}", "Codigo QR incluido en el mensaje."),
        (qr_code, "Codigo QR incluido en el mensaje."),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def _render_email_body_html(value, qr_code):
    html = _multiline_html(value)
    replacements = [
        (f"QR: {qr_code}", "Codigo QR visible al final del correo."),
        (qr_code, "Codigo QR visible al final del correo."),
    ]
    for source, target in replacements:
        html = html.replace(escape(source), escape(target))
    return html


def _normalize_datetime(value):
    if hasattr(value, "strftime"):
        if is_naive(value):
            return make_aware(value)
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if is_naive(parsed):
        return make_aware(parsed)
    return parsed


def _file_to_png_bytes(field_file):
    if not field_file:
        return None
    try:
        field_file.open("rb")
        with Image.open(field_file) as image:
            buffer = BytesIO()
            image.convert("RGBA").save(buffer, format="PNG")
        field_file.close()
        return buffer.getvalue()
    except FileNotFoundError:
        return None


def _file_to_bytes(field_file):
    if not field_file:
        return None
    try:
        field_file.open("rb")
        content = field_file.read()
        field_file.close()
        return content
    except FileNotFoundError:
        return None


def _image_mimetype(field_file, default="image/png"):
    if not field_file:
        return default
    name = str(getattr(field_file, "name", "") or "").lower()
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    return default


def _absolute_media_url(url):
    if not url:
        return ""
    if str(url).startswith(("http://", "https://")):
        return str(url)
    base_url = getattr(settings, "EMAIL_MEDIA_BASE_URL", "").rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}{url}"


def _field_url(field_file):
    if not field_file:
        return ""
    try:
        return field_file.url
    except ValueError:
        return ""


def _build_event_rendered_content(event, attendee):
    price_text = _format_price(attendee.category.price)
    starts_at = _normalize_datetime(event.starts_at)
    formatted_date = starts_at.strftime("%d/%m/%Y %H:%M") if starts_at else str(event.starts_at)
    formatted_time = starts_at.strftime("%I:%M %p").lstrip("0") if starts_at else str(event.starts_at)
    context = SafeFormatDict(
        {
            "attendee_name": attendee.name,
            "nombre_asistente": attendee.name,
            "event_name": event.name,
            "nombre_evento": event.name,
            "branch_name": attendee.branch.name,
            "nombre_sucursal": attendee.branch.name,
            "event_date": formatted_date,
            "fecha_evento": formatted_date,
            "event_time": formatted_time,
            "hora_evento": formatted_time,
            "category_name": attendee.category.name,
            "nombre_categoria": attendee.category.name,
            "qr_code": attendee.qr_code,
            "codigo_qr": attendee.qr_code,
            "attendee_cc": attendee.cc,
            "cedula_asistente": attendee.cc,
            "category_price": price_text,
            "precio_categoria": price_text,
            "venue_name": event.venue_name,
        }
    )

    rendered = {
        "subject": (event.email_subject or "Tu acceso esta listo: {event_name}").format_map(context),
        "preheader": (event.email_preheader or "").format_map(context),
        "heading": (event.email_heading or "Hola {attendee_name}").format_map(context),
        "intro": (event.email_intro or "").format_map(context),
        "message_title": (event.email_message_title or "Mensaje del evento").format_map(context),
        "body": _remove_branch_lines((event.email_body or "").format_map(context)),
        "warning_title": (event.email_warning_title or "Importante").format_map(context),
        "warning_text": (event.email_warning_text or "").format_map(context),
        "details_title": (event.email_details_title or "Detalles").format_map(context),
        "date_text": (event.email_date_text or "{fecha_evento}").format_map(context),
        "time_text": (event.email_time_text or "{hora_evento}").format_map(context),
        "venue_name": (event.venue_name or "").format_map(context),
        "maps_label": (event.maps_label or "Abrir en Google Maps").format_map(context),
        "dress_code": (event.dress_code or "").format_map(context),
        "qr_title": (event.email_qr_title or "").format_map(context),
        "qr_note": (event.email_qr_note or "").format_map(context),
        "footer": (event.email_footer or "").format_map(context),
        "closing_text": (event.email_closing_text or "").format_map(context),
        "team_signature": (event.email_team_signature or "").format_map(context),
        "legal_note": (event.email_legal_note or "").format_map(context),
    }
    return rendered, price_text


def build_event_share_text(event, attendee, qr_url="", flyer_url=""):
    rendered, price_text = _build_event_rendered_content(event, attendee)
    parts = [
        rendered["heading"],
        rendered["intro"],
        _render_email_body_text(rendered["body"], attendee.qr_code),
        f'{rendered["warning_title"]}: {rendered["warning_text"]}' if rendered["warning_text"] else "",
        f"Evento: {event.name}",
        f"Fecha: {rendered['date_text']}",
        f"Hora: {rendered['time_text']}",
        f"Lugar: {rendered['venue_name']}",
        f"Categoria: {attendee.category.name}",
        f"Precio: {price_text}",
        rendered["qr_title"],
        rendered["qr_note"],
        qr_url,
        flyer_url,
        rendered["footer"],
        rendered["closing_text"],
        rendered["team_signature"],
    ]
    return "\n\n".join(part.strip() for part in parts if str(part or "").strip())


def build_whatsapp_share_card_png(attendee):
    canvas = Image.new("RGB", (1200, 630), color="#0f2430")
    draw = ImageDraw.Draw(canvas)

    flyer_file = resolve_field_file(attendee.event, "flyer", "event_flyer") or getattr(attendee.event, "flyer", None)
    qr_file = resolve_field_file(attendee, "qr_image", "attendee_qr") or getattr(attendee, "qr_image", None)

    if flyer_file:
        try:
            flyer_file.open("rb")
            with Image.open(flyer_file) as flyer_image:
                flyer = flyer_image.convert("RGB")
            flyer_file.close()
            flyer = ImageOps.fit(flyer, (1200, 630), method=Image.Resampling.LANCZOS)
            flyer = Image.blend(flyer, Image.new("RGB", (1200, 630), "#08141b"), 0.42)
            canvas.paste(flyer, (0, 0))
        except (FileNotFoundError, ValueError):
            pass

    overlay = Image.new("RGBA", (1200, 630), (8, 16, 22, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle((40, 40, 760, 590), radius=36, fill=(9, 19, 27, 220))
    overlay_draw.rounded_rectangle((820, 75, 1125, 380), radius=34, fill=(0, 0, 0, 235))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.text((86, 92), attendee.event.name, fill="#ffffff", font=title_font)
    draw.text((86, 150), f"Asistente: {attendee.name}", fill="#d7f6df", font=body_font)
    draw.text((86, 188), f"Categoria: {attendee.category.name}", fill="#d7f6df", font=body_font)
    draw.text((86, 226), f"Cedula: {attendee.cc}", fill="#d7f6df", font=body_font)
    if attendee.event.starts_at:
        starts_at = _normalize_datetime(attendee.event.starts_at)
        if starts_at:
            draw.text((86, 264), f"Fecha: {starts_at.strftime('%d/%m/%Y %I:%M %p').lstrip('0')}", fill="#d7f6df", font=body_font)
    draw.text((86, 334), attendee.event.email_footer or "Presenta este acceso en la entrada.", fill="#ffe08a", font=body_font)
    draw.text((86, 372), attendee.event.email_team_signature or f"Equipo {attendee.event.name}", fill="#ffffff", font=body_font)

    if qr_file:
        try:
            qr_file.open("rb")
            with Image.open(qr_file) as qr_image:
                qr = qr_image.convert("RGB")
            qr_file.close()
            qr = ImageOps.contain(qr, (250, 250), method=Image.Resampling.LANCZOS)
            qr_panel = Image.new("RGB", (278, 278), "#000000")
            qr_panel.paste(qr, ((278 - qr.width) // 2, (278 - qr.height) // 2))
            canvas.paste(qr_panel, (834, 90))
        except (FileNotFoundError, ValueError):
            pass

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def build_event_email_payload(event, attendee, flyer_cid="", flyer_data_uri="", flyer_url="", qr_cid="", qr_data_uri=""):
    rendered, price_text = _build_event_rendered_content(event, attendee)

    flyer_html = ""
    if flyer_url:
        flyer_html = """
            <div class="flyer-wrapper">
                <img src="{flyer_url}" alt="Flyer del evento">
            </div>
        """.format(flyer_url=escape(flyer_url))
    elif flyer_cid:
        flyer_html = """
            <div class="flyer-wrapper">
                <img src="cid:{flyer_cid}" alt="Flyer del evento">
            </div>
        """.format(flyer_cid=escape(flyer_cid))
    elif flyer_data_uri:
        flyer_html = """
            <div class="flyer-wrapper">
                <img src="{flyer_data_uri}" alt="Flyer del evento">
            </div>
        """.format(flyer_data_uri=flyer_data_uri)

    qr_html = ""
    if qr_cid:
        qr_html = """
            <div class="qr-wrapper">
                <div class="qr-frame">
                    <img src="cid:{qr_cid}" alt="Codigo QR">
                </div>
            </div>
        """.format(qr_cid=escape(qr_cid))
    elif qr_data_uri:
        qr_html = """
            <div class="qr-wrapper">
                <div class="qr-frame">
                    <img src="{qr_data_uri}" alt="Codigo QR">
                </div>
            </div>
        """.format(qr_data_uri=qr_data_uri)

    maps_html = "<span>No configurada</span>"
    if event.maps_url:
        maps_html = f'<a href="{escape(event.maps_url)}">{escape(rendered["maps_label"])}</a>'

    text_content = "\n\n".join(
        part
        for part in [
            rendered["heading"],
            rendered["intro"],
            rendered["body"],
            f'{rendered["warning_title"]}: {rendered["warning_text"]}' if rendered["warning_text"] else "",
            f"Evento: {event.name}",
            f'Fecha: {rendered["date_text"]}',
            f'Hora: {rendered["time_text"]}',
            f'Lugar: {rendered["venue_name"]}',
            f'Dress code: {rendered["dress_code"]}',
            "Codigo QR visible al final del correo y adjunto como imagen.",
            rendered["qr_note"],
            rendered["footer"],
            rendered["closing_text"],
            rendered["team_signature"],
        ]
        if part
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="x-apple-disable-message-reformatting">
      <title>{escape(rendered["subject"])}</title>
      <style>
        body, p, h1, h2, h3 {{ margin: 0; padding: 0; }}
        body {{
          background: {event.email_background_color};
          color: {event.email_text_color};
          font-family: Arial, sans-serif;
          line-height: 1.6;
          padding: 24px 0;
        }}
        a {{ color: {event.email_accent_color}; text-decoration: none; }}
        .container {{
          max-width: 600px;
          margin: 0 auto;
          background: {event.email_card_color};
          border-radius: 20px;
          overflow: hidden;
          border: 1px solid {event.email_border_color};
        }}
        .header {{
          padding: 32px 24px;
          background: {event.email_header_background_color};
          border-bottom: 1px solid {event.email_border_color};
          text-align: center;
        }}
        .header h1 {{
          color: {event.email_accent_color};
          font-size: 28px;
          margin-bottom: 10px;
        }}
        .header p {{
          color: {event.email_muted_text_color};
        }}
        .content {{
          padding: 24px;
        }}
        .copy {{
          margin-bottom: 20px;
        }}
        .copy h2 {{
          color: {event.email_text_color};
          margin-bottom: 10px;
        }}
        .copy p {{
          color: {event.email_text_color};
        }}
        .box {{
          border: 1px solid {event.email_border_color};
          border-radius: 16px;
          padding: 16px 18px;
          margin-bottom: 18px;
          background: {event.email_section_background_color};
          color: #f3f3f3;
        }}
        .box strong,
        .ticket strong {{
          color: #ffffff;
        }}
        .highlight {{
          border-left: 4px solid {event.email_accent_color};
        }}
        .box-title {{
          color: {event.email_accent_color};
          font-weight: 700;
          display: block;
          margin-bottom: 8px;
        }}
        .warning {{
          background: {event.email_warning_background_color};
        }}
        .flyer-wrapper {{
          margin: 0 0 18px;
          border: 1px solid {event.email_border_color};
          border-radius: 16px;
          overflow: hidden;
        }}
        .flyer-wrapper img {{
          display: block;
          width: 100%;
          height: auto;
        }}
        .details p,
        .ticket p {{
          margin-bottom: 6px;
        }}
        .ticket {{
          text-align: center;
          border-style: dashed;
        }}
        .qr-wrapper {{
          text-align: center;
          margin: 18px auto 0;
        }}
        .qr-frame {{
          display: inline-block;
          background: #000000;
          border-radius: 22px;
          padding: 18px;
        }}
        .qr-wrapper img {{
          display: block;
          margin: 0 auto;
          width: 260px;
          height: 260px;
          background: #ffffff;
          border-radius: 16px;
          padding: 12px;
        }}
        .ticket-title,
        .closing-brand {{
          color: {event.email_accent_color};
          font-weight: 700;
        }}
        .muted {{
          color: {event.email_muted_text_color};
        }}
        .footer {{
          border-top: 1px solid {event.email_border_color};
          padding: 18px 24px 24px;
          text-align: center;
          color: {event.email_muted_text_color};
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>{escape(event.name)}</h1>
          <p>{escape(rendered["preheader"])}</p>
        </div>
        <div class="content">
          <div class="copy">
            <h2>{escape(rendered["heading"])}</h2>
            <p>{_multiline_html(rendered["intro"])}</p>
          </div>

          <div class="box highlight">
            <span class="box-title">{escape(rendered["message_title"])}</span>
            <div>{_render_email_body_html(rendered["body"], attendee.qr_code)}</div>
          </div>

          <div class="box warning">
            <span class="box-title">{escape(rendered["warning_title"])}</span>
            <div>{_multiline_html(rendered["warning_text"])}</div>
          </div>
          {flyer_html}
          <div class="box details">
            <span class="box-title">{escape(rendered["details_title"])}</span>
            <p><strong>Evento:</strong> {escape(event.name)}</p>
            <p><strong>Fecha:</strong> {escape(rendered["date_text"])}</p>
            <p><strong>Hora:</strong> {escape(rendered["time_text"])}</p>
            <p><strong>Lugar:</strong> {escape(rendered["venue_name"])}</p>
            <p><strong>Ubicacion:</strong> {maps_html}</p>
            <p><strong>Dress code:</strong> <span class="closing-brand">{escape(rendered["dress_code"])}</span></p>
          </div>

          <div class="box ticket">
            <p><strong>Nombre:</strong> {escape(attendee.name)}</p>
            <p><strong>Cedula:</strong> {escape(attendee.cc)}</p>
            <p><strong>Categoria:</strong> {escape(attendee.category.name)}</p>
            <p><strong>Precio:</strong> {escape(price_text)}</p>
            <p class="ticket-title">{escape(rendered["qr_title"])}</p>
            <p class="muted">{escape(rendered["qr_note"])}</p>
          </div>

          <div class="copy">
            <p class="closing-brand">{escape(rendered["footer"])}</p>
            <p>{escape(rendered["closing_text"])}</p>
            <p class="closing-brand">{escape(rendered["team_signature"])}</p>
          </div>

          {qr_html}
        </div>
        <div class="footer">
          <p>{escape(rendered["legal_note"])}</p>
        </div>
      </div>
    </body>
    </html>
    """

    return {
        "subject": rendered["subject"],
        "text_content": text_content,
        "html_content": html_content,
    }


def send_attendee_ticket_email(attendee):
    if not attendee.email:
        return False, "El asistente no tiene correo."

    if not attendee.qr_image:
        generate_attendee_qr(attendee)

    flyer_file = resolve_field_file(attendee.event, "flyer", "event_flyer") or getattr(attendee.event, "flyer", None)
    flyer_png = _file_to_png_bytes(flyer_file)
    flyer_cid = "event_flyer_inline" if flyer_png else ""

    qr_file = resolve_field_file(attendee, "qr_image", "attendee_qr") or getattr(attendee, "qr_image", None)
    qr_bytes = _file_to_png_bytes(qr_file)
    if not qr_bytes:
        qr_bytes = build_qr_png_bytes(attendee.qr_code, attendee.event, attendee.branch)
    qr_cid = "event_qr_inline" if qr_bytes else ""
    payload = build_event_email_payload(
        attendee.event,
        attendee,
        flyer_cid=flyer_cid,
        qr_cid=qr_cid,
    )

    email = RelatedEmailMultiAlternatives(
        subject=payload["subject"],
        body=payload["text_content"],
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[attendee.email],
    )
    email.attach_alternative(payload["html_content"], "text/html")

    if qr_bytes:
        email.attach_inline_image(
            qr_bytes,
            qr_cid,
            f"{attendee.qr_code}.png",
            mimetype="image/png",
        )
    if flyer_png:
        email.attach_inline_image(
            flyer_png,
            flyer_cid,
            f"{attendee.event.slug or attendee.event.pk}-flyer.png",
            mimetype="image/png",
        )
    email.send()
    return True, "Correo enviado."
