import uuid
import qrcode
from io import BytesIO
from django.core.files import File
from django.db import models
from django.contrib.auth.models import User, Group
from PIL import Image


class PerfilUsuario(models.Model):
    """
    Perfil extendido para usuarios del sistema con roles específicos
    """

    ROLES = [
        ("entrada", "Personal de Entrada"),
        ("barra", "Personal de Barra"),
        ("admin", "Administrador"),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=20, choices=ROLES)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Asignar al grupo correspondiente automáticamente
        self.usuario.groups.clear()
        group_name = self.get_rol_display()
        group, created = Group.objects.get_or_create(name=group_name)
        self.usuario.groups.add(group)

    def __str__(self):
        return f"{self.usuario.username} - {self.get_rol_display()}"


class Categoria(models.Model):
    """
    Categorías de asistentes con diferentes beneficios
    """

    nombre = models.CharField(max_length=50, unique=True)
    consumos_incluidos = models.IntegerField(default=0)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return f"{self.nombre} ({self.consumos_incluidos} consumos)"


class Asistente(models.Model):
    """
    Registro de asistentes al evento
    """

    nombre = models.CharField(max_length=100)
    cc = models.CharField(
        max_length=20, unique=True, primary_key=True, verbose_name="Cédula"
    )
    numero = models.CharField(max_length=20, verbose_name="Teléfono")
    correo = models.EmailField()
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)

    # Campos QR
    codigo_qr = models.CharField(max_length=100, unique=True, blank=True)
    qr_image = models.ImageField(upload_to="qr_codes/", blank=True)

    # Control entrada
    ha_ingresado = models.BooleanField(default=False)
    fecha_ingreso = models.DateTimeField(null=True, blank=True)
    usuario_entrada = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingresos_verificados",
    )

    # Consumos
    consumos_disponibles = models.IntegerField(default=0)

    # Metadatos
    fecha_registro = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asistentes_creados",
    )

    class Meta:
        verbose_name = "Asistente"
        verbose_name_plural = "Asistentes"
        ordering = ["-fecha_registro"]

    def save(self, *args, **kwargs):
        # Generar código QR único si no existe
        if not self.codigo_qr:
            self.codigo_qr = str(uuid.uuid4())

        # Asignar consumos según categoría si no están asignados
        if not self.consumos_disponibles:
            self.consumos_disponibles = self.categoria.consumos_incluidos

        super().save(*args, **kwargs)

        # Generar imagen QR si no existe
        if not self.qr_image:
            self.generar_qr()

    # En core/models.py - Solo reemplaza el método generar_qr() existente

    def generar_qr(self):
        """Genera la imagen QR para el asistente con logo DMT.png en el centro"""
        import qrcode
        from io import BytesIO
        from django.core.files import File
        from PIL import Image, ImageDraw, ImageFont
        import os
        from django.conf import settings
        
        # Generar QR básico con mayor corrección de errores para soportar logo central
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Alta corrección para logo central
            box_size=10,
            border=4,
        )
        qr.add_data(self.codigo_qr)
        qr.make(fit=True)

        # Crear imagen QR con colores personalizados
        qr_img = qr.make_image(
            fill_color="#1a4a1a",      # Verde oscuro para el QR
            back_color="#f0f8f0"       # Fondo verde muy claro
        )
        qr_img = qr_img.convert("RGBA")
        
        # Redimensionar QR a un tamaño más grande
        qr_size = 400
        qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        
        # === LOGO DMT.PNG EN EL CENTRO DEL QR ===
        try:
            # Buscar DMT.png en diferentes ubicaciones posibles
            possible_paths = [
                os.path.join(settings.BASE_DIR, 'static', 'images', 'DMT.png'),
                os.path.join(settings.BASE_DIR, 'static', 'DMT.png'),
                os.path.join(settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else '', 'images', 'DMT.png'),
                os.path.join(settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else '', 'DMT.png'),
            ]
            
            watermark_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    watermark_path = path
                    break
            
            if watermark_path:
                # Cargar logo
                logo = Image.open(watermark_path).convert("RGBA")
                
                # Calcular tamaño del logo (aproximadamente 20% del QR)
                logo_size = int(qr_size * 0.2)  # 20% del tamaño del QR
                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                
                # Crear fondo circular verde oscuro para el logo
                circle_size = logo_size + 20  # Un poco más grande que el logo
                circle_img = Image.new('RGBA', (circle_size, circle_size), (0, 0, 0, 0))
                circle_draw = ImageDraw.Draw(circle_img)
                
                # Dibujar círculo con borde
                circle_draw.ellipse([0, 0, circle_size-1, circle_size-1], 
                                fill=(26, 74, 26, 255),      # Verde oscuro de fondo
                                outline=(240, 248, 240, 255), # Borde claro
                                width=3)
                
                # Calcular posición central
                qr_center_x = qr_size // 2
                qr_center_y = qr_size // 2
                
                # Posición del círculo (centrado)
                circle_x = qr_center_x - circle_size // 2
                circle_y = qr_center_y - circle_size // 2
                
                # Posición del logo (centrado dentro del círculo)
                logo_x = qr_center_x - logo_size // 2
                logo_y = qr_center_y - logo_size // 2
                
                # Pegar el círculo de fondo primero
                qr_img.paste(circle_img, (circle_x, circle_y), circle_img)
                
                # Pegar el logo encima del círculo
                qr_img.paste(logo, (logo_x, logo_y), logo)
                
                print(f"Logo DMT.png aplicado en el centro desde: {watermark_path}")
            else:
                print("DMT.png no encontrado, QR sin logo central")
                
        except Exception as e:
            print(f"Error cargando DMT.png: {e}, QR sin logo central")
        
        # Crear imagen final con información adicional abajo
        final_height = qr_size + 80  # Espacio extra para información
        final_img = Image.new('RGBA', (qr_size, final_height), (240, 248, 240, 255))  # Fondo verde claro
        
        # Pegar QR en la parte superior
        final_img.paste(qr_img, (0, 0))
        
        # Agregar información del asistente abajo
        draw = ImageDraw.Draw(final_img)
        
        try:
            # Intentar usar fuente personalizada
            font_title = ImageFont.truetype("arial.ttf", 18) if os.name == 'nt' else ImageFont.load_default()
            font_info = ImageFont.truetype("arial.ttf", 12) if os.name == 'nt' else ImageFont.load_default()
        except:
            font_title = ImageFont.load_default()
            font_info = ImageFont.load_default()
        
        # Posiciones para el texto
        y_start = qr_size + 10
        
        # Información del evento
        evento_text = f"DMT 69 - Evento xxxx"
        
        # Centrar texto del evento
        text_width = draw.textlength(evento_text, font=font_title)
        x_center = (qr_size - text_width) // 2
        draw.text((x_center, y_start), evento_text, fill=(26, 74, 26, 255), font=font_title)
        
        # Centrar texto de categoría
        
        # Código QR pequeño abajo
        
        # Convertir a RGB para guardar
        final_img = final_img.convert('RGB')
        
        # Guardar en buffer
        buffer = BytesIO()
        final_img.save(buffer, 'PNG', quality=95)
        buffer.seek(0)

        # Guardar en el modelo
        filename = f"qr_{self.cc}.png"
        self.qr_image.save(filename, File(buffer), save=False)
        self.save(update_fields=["qr_image"])

    def __str__(self):
        return f"{self.nombre} - {self.cc}"


class Producto(models.Model):
    """
    Productos disponibles en la barra
    """

    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=5)
    activo = models.BooleanField(default=True)

    # Metadatos
    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} - ${self.precio}"

    @property
    def necesita_stock(self):
        """Indica si el producto necesita reposición"""
        return self.stock <= self.stock_minimo

    @property
    def estado_stock(self):
        """Retorna el estado del stock como texto"""
        if self.stock == 0:
            return "Agotado"
        elif self.necesita_stock:
            return "Stock Bajo"
        else:
            return "Disponible"


class MovimientoStock(models.Model):
    """
    Registro de movimientos de inventario
    """

    TIPOS = [
        ("entrada", "Entrada de Stock"),
        ("salida", "Salida de Stock"),
        ("ajuste", "Ajuste de Inventario"),
        ("venta", "Venta"),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    cantidad = models.IntegerField()
    stock_anterior = models.IntegerField()
    stock_nuevo = models.IntegerField()
    observacion = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Movimiento de Stock"
        verbose_name_plural = "Movimientos de Stock"
        ordering = ["-fecha"]

    def save(self, *args, **kwargs):
        # Guardar stock anterior
        self.stock_anterior = self.producto.stock

        super().save(*args, **kwargs)

        # Actualizar stock del producto
        if self.tipo == "entrada":
            self.producto.stock += self.cantidad
        elif self.tipo in ["salida", "venta"]:
            self.producto.stock -= self.cantidad
        elif self.tipo == "ajuste":
            self.producto.stock = self.cantidad

        # Guardar stock nuevo
        self.stock_nuevo = self.producto.stock
        self.producto.save(update_fields=["stock"])

        # Actualizar el registro con el stock nuevo
        MovimientoStock.objects.filter(pk=self.pk).update(stock_nuevo=self.stock_nuevo)

    def __str__(self):
        return f"{self.producto.nombre} - {self.get_tipo_display()} - {self.cantidad}"


class VentaBarra(models.Model):
    """
    Registro de ventas en la barra
    """

    asistente = models.ForeignKey(
        Asistente, on_delete=models.SET_NULL, null=True, blank=True
    )
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    usa_consumo_incluido = models.BooleanField(default=False)

    # Metadatos
    fecha = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ["-fecha"]

    def save(self, *args, **kwargs):
        # Calcular total
        self.total = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

        # Crear movimiento de stock
        MovimientoStock.objects.create(
            producto=self.producto,
            tipo="venta",
            cantidad=self.cantidad,
            observacion=f'Venta a {self.asistente.nombre if self.asistente else "Cliente general"}',
            usuario=self.vendedor,
        )

        # Si usa consumo incluido, descontar del asistente
        if self.usa_consumo_incluido and self.asistente:
            self.asistente.consumos_disponibles -= self.cantidad
            self.asistente.save(update_fields=["consumos_disponibles"])

    def __str__(self):
        cliente = self.asistente.nombre if self.asistente else "Cliente General"
        return f"Venta a {cliente} - {self.producto.nombre} x{self.cantidad}"


# Signals para crear grupos automáticamente
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def crear_grupos_y_permisos(sender, **kwargs):
    """Crear grupos de permisos automáticamente después de migrar"""
    if sender.name == "core":
        # Crear grupos
        Group.objects.get_or_create(name="Personal de Entrada")
        Group.objects.get_or_create(name="Personal de Barra")
        Group.objects.get_or_create(name="Administrador")
