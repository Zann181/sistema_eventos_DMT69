# core/email_utils.py (VERSIÓN SIN MODIFICAR MODELO)

from django.core.mail import EmailMessage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def enviar_email_bienvenida(asistente):
    """Envía email de bienvenida con QR al asistente"""
    try:
        # Obtener solo el primer nombre
        primer_nombre = asistente.nombre.split()[0]
        
        # Crear mensaje HTML simple
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; }}
                .header {{ background: #1a4a1a; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ padding: 30px; background: white; border-radius: 0 0 10px 10px; }}
                .event-info {{ background: #e8f5e8; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 5px solid #1a4a1a; }}
                .qr-info {{ background: #f0f8ff; padding: 20px; margin: 20px 0; border-radius: 8px; text-align: center; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; }}
                h1 {{ margin: 0; font-size: 2.2em; }}
                h2 {{ color: #1a4a1a; margin-top: 0; }}
                h3 {{ color: #1a4a1a; margin-bottom: 10px; }}
                .highlight {{ color: #1a4a1a; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 {getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')} 🎉</h1>
                </div>
                
                <div class="content">
                    <h2>¡Hola {primer_nombre}!</h2>
                    
                    <p>Gracias por registrarte en <span class="highlight">{getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')}</span>. 
                    Tu entrada ha sido confirmada exitosamente y estamos emocionados de tenerte con nosotros.</p>
                    
                    <div class="event-info">
                        <h3>📅 Detalles del Evento:</h3>
                        <p><strong>🎵 Evento:</strong> {getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')}</p>
                        <p><strong>📅 Fecha:</strong> {getattr(settings, 'EVENTO_FECHA', '31 de Diciembre 2025')}</p>
                        <p><strong>🕙 Hora:</strong> {getattr(settings, 'EVENTO_HORA', '10:00 PM')}</p>
                        <p><strong>📍 Lugar:</strong> {getattr(settings, 'EVENTO_LUGAR', 'Mocoa, Putumayo')}</p>
                    </div>
                    
                    <div class="qr-info">
                        <h3>🎫 Tu Información de Entrada</h3>
                        <p><strong>Nombre:</strong> {asistente.nombre}</p>
                        <p><strong>Cédula:</strong> {asistente.cc}</p>
                        <p><strong>Categoría:</strong> {asistente.categoria.nombre}</p>
                        <p style="color: #d9534f; font-weight: bold;">📱 Tu código QR está adjunto a este correo</p>
                        <p><small>Presenta tu cédula y el código QR en la entrada del evento</small></p>
                    </div>
                    
                    <p>¡Te esperamos para vivir una experiencia inolvidable en <span class="highlight">{getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')}</span>!</p>
                    
                    <div class="footer">
                        <p><strong>Equipo {getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')}</strong></p>
                        <p><small>Este es un email automático. Conserva tu código QR hasta el día del evento.</small></p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Crear email
        subject = f"✅ ¡Bienvenido {primer_nombre}! Tu entrada para {getattr(settings, 'EVENTO_NOMBRE', 'DMT 69')} está lista"
        
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[asistente.correo],
        )
        email.content_subtype = "html"  # Para que interprete HTML
        
        # Adjuntar QR si existe
        if asistente.qr_image:
            try:
                with open(asistente.qr_image.path, 'rb') as qr_file:
                    email.attach(f"QR_{primer_nombre}_{asistente.cc}.png", qr_file.read(), 'image/png')
            except Exception as e:
                logger.warning(f"No se pudo adjuntar QR: {e}")
        
        # Enviar
        email.send()
        logger.info(f"Email enviado a {asistente.correo} ({primer_nombre})")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando email a {asistente.correo}: {str(e)}")
        print(f"Error detallado: {e}")  # Para debug
        return False