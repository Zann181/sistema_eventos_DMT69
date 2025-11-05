# core/email_utils.py (PLANTILLA MOCOA BEATS, FIX COLOR <strong> + FLYER EMBEBIDO)

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.conf import settings
import logging
import os
from email.mime.image import MIMEImage

logger = logging.getLogger(__name__)

def enviar_email_bienvenida(asistente):
    """Envía email de bienvenida con QR al asistente"""
    try:
        # Datos básicos y fallbacks seguros
        primer_nombre = (asistente.nombre or "").split()[0] if getattr(asistente, "nombre", None) else "Invitado"
        correo = getattr(asistente, "correo", None)
        cc = getattr(asistente, "cc", "")
        categoria_nombre = getattr(getattr(asistente, "categoria", None), "nombre", "General")
        qr_field = getattr(asistente, "qr_image", None)
        qr_path = getattr(qr_field, "path", None) if qr_field else None

        # HTML tema oscuro + EXOS bold + <strong> hereda color + FLYER embebido
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="x-apple-disable-message-reformatting">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                /* Reset básico para consistencia en clientes de correo */
                body, p, h1, h2, h3, h4, h5, h6 {{ margin: 0; padding: 0; }}
                img {{ border: 0; outline: none; text-decoration: none; max-width: 100%; }}
                table {{ border-collapse: collapse; }}
                a {{ color: #00baff; text-decoration: none; }}

                body {{
                    background-color: #0e0e0f;
                    color: #d0d0d0;
                    font-family: 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 0;
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #131415;
                    border-radius: 10px;
                    overflow: hidden;
                    border: 1px solid #1f1f22;
                }}
                .header {{
                    text-align: center;
                    background: #0e0e0f;
                    padding: 40px 20px 30px 20px;
                    color: #e1e1e1;
                    border-bottom: 1px solid #1f1f22;
                }}
                .header h1 {{
                    font-size: 1.9em;
                    letter-spacing: 0.5px;
                    color: #00baff;
                    font-weight: 500;
                    margin: 0;
                }}
                .content {{
                    padding: 30px 25px;
                    color: #bdbdbd;
                    font-size: 15px;
                }}
                h2 {{
                    color: #ffffff;
                    margin-top: 0;
                    font-size: 1.3em;
                    font-weight: 500;
                }}
                .event-info {{
                    margin: 25px 0;
                    background: #18191b;
                    border: 1px solid #1f1f22;
                    border-left: 3px solid #00baff;
                    border-radius: 8px;
                    padding: 18px 22px;
                }}
                .event-info h3 {{
                    color: #00baff;
                    margin: 0 0 8px 0;
                    font-size: 1.1em;
                    font-weight: 600;
                }}
                .qr-info {{
                    text-align: center;
                    margin: 25px 0;
                    padding: 20px;
                    border: 1px dashed #00baff;
                    border-radius: 8px;
                    background: #151617;
                }}
                .footer {{
                    text-align: center;
                    font-size: 0.9em;
                    color: #7d7d7d;
                    padding: 25px;
                    border-top: 1px solid #1f1f22;
                }}
                /* FIX: que <strong> NO cambie el color (hereda del padre) */
                strong {{ color: inherit; font-weight: 700; }}
                .highlight {{ color: #00baff; font-weight: 600; }}
                /* Aseguramos el color base de párrafos y listas dentro de content */
                .content p, .content li {{ color: #bdbdbd; }}
                .flyer-wrapper {{ text-align:center; margin: 20px 0 5px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1><strong>EXOS</strong> "𝐌𝐨𝐜𝐨𝐚 𝐁𝐞𝐚𝐭𝐬" 🍃🧬</h1>
                </div>
                <div class="content">
                    <h2>¡Bienvenido {primer_nombre}!</h2>

                    <p>Tu asistencia ha sido confirmada para disfrutar este <strong>8 de noviembre</strong> de las <span class="highlight">frecuencias nórdicas</span> en la selva.
                    Una experiencia de <strong>música de avanzada</strong> te espera en <span class="highlight">𝐌𝐨𝐜𝐨𝐚 𝐁𝐞𝐚𝐭𝐬</span>.</p>

                    <p>Desde las tierras del fuego, hielo y auroras 🇮🇸🌋🌌 tenemos el honor de recibir nuevamente a <strong>@exos_____</strong>,
                    junto a <strong>@a.30.col</strong> en formato Live 🎹 y <strong>@mdr.rcol</strong> representando la casa 🍃👁️.</p>

                    <!-- FLYER EMBEBIDO -->
                    <div class="flyer-wrapper">
                        <img src="cid:flyer_mocoabeats" alt="Flyer Mocoa Beats" style="border-radius:10px; max-width:100%; height:auto;" />
                    </div>

                    <div class="event-info">
                        <h3>Detalles del Evento</h3>
                        <p><strong>Evento:</strong> 𝐌𝐨𝐜𝐨𝐚 𝐁𝐞𝐚𝐭𝐬</p>
                        <p><strong>Fecha:</strong> Sábado 8 de Noviembre</p>
                        <p><strong>Hora:</strong> 9:00 PM</p>
                        <p><strong>Lugar:</strong> Mocoa, Putumayo</p>
                    </div>

                    <div class="qr-info">
                        <p><strong>Nombre:</strong> {asistente.nombre}</p>
                        <p><strong>Cédula:</strong> {cc}</p>
                        <p><strong>Categoría:</strong> {categoria_nombre}</p>
                        <p><strong>Precio: </strong> {asistente.consumos_disponibles}</p>
                        <p style="color:#00baff;font-weight:bold;">📱 Tu código QR está adjunto a este correo</p>
                        <p><small>Preséntalo junto a tu cédula en la entrada del evento.</small></p>
                    </div>

                    <p>Nos vemos en la selva.<br>
                    <span class="highlight">Musica electronica avanzada en Mocoa 🍃</span></p>
                </div>
                <div class="footer">
                    <p>Equipo 𝐌𝐨𝐜𝐨𝐚 𝐁𝐞𝐚𝐭𝐬</p>
                    <p><small>Correo automático — conserva tu QR hasta el día del evento.</small></p>
                </div>
            </div>
        </body>
        </html>
        """

        subject = f"🎫 Tu entrada está lista, {primer_nombre} — 𝐌𝐨𝐜𝐨𝐚 𝐁𝐞𝐚𝐭𝐬"

        if not correo:
            raise ValueError("El asistente no tiene correo definido.")

        # Usamos EmailMultiAlternatives para mejor control de MIME multipart/related
        text_content = f"Hola {primer_nombre}, tu entrada para Mocoa Beats está lista."
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[correo],
        )
        email.attach_alternative(html_content, "text/html")
        email.mixed_subtype = "related"

        # Adjuntar QR si existe
        if qr_path and os.path.exists(qr_path):
            try:
                with open(qr_path, "rb") as qr_file:
                    email.attach(f"QR_{primer_nombre}_{cc}.png", qr_file.read(), "image/png")
            except Exception as e:
                logger.warning(f"No se pudo adjuntar QR: {e}")

        # Adjuntar flyer embebido (inline)
        try:
            flyer_path = os.path.join(settings.BASE_DIR, "static", "images", "flyer.png")
            # Si tu carpeta es “imagen” en vez de “images”, cámbialo
            if not os.path.exists(flyer_path):
                flyer_path = os.path.join(settings.BASE_DIR, "static", "imagen", "flyer.png")
            if os.path.exists(flyer_path):
                with open(flyer_path, "rb") as f:
                    flyer = MIMEImage(f.read())
                    flyer.add_header("Content-ID", "<flyer_mocoabeats>")
                    flyer.add_header("Content-Disposition", "inline", filename="flyer.png")
                    email.attach(flyer)
            else:
                logger.warning(f"Flyer no encontrado en {flyer_path}")
        except Exception as e:
            logger.warning(f"No se pudo adjuntar flyer inline: {e}")

        # Enviar
        email.send()
        logger.info(f"Email enviado a {correo} ({primer_nombre})")
        return True

    except Exception as e:
        logger.error(f"Error enviando email a {getattr(asistente, 'correo', 'sin_correo')}: {str(e)}")
        print(f"Error detallado: {e}")
        return False
