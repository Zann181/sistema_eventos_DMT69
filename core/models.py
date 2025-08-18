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

    def generar_qr(self):
        """Genera la imagen QR para el asistente"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.codigo_qr)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, "PNG")
        buffer.seek(0)

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
