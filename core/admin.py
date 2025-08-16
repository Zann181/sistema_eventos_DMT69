from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import PerfilUsuario, Categoria, Asistente, Producto, MovimientoStock, VentaBarra

# Configurar el perfil de usuario inline
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil'

# Extender el admin de User para incluir el perfil
class UserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline,)
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'get_rol']
    
    def get_rol(self, obj):
        try:
            return obj.perfilusuario.get_rol_display()
        except:
            return "Sin rol"
    get_rol.short_description = 'Rol'

# Re-registrar UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'rol', 'activo', 'fecha_creacion']
    list_filter = ['rol', 'activo', 'fecha_creacion']
    search_fields = ['usuario__username', 'usuario__email', 'usuario__first_name', 'usuario__last_name']
    readonly_fields = ['fecha_creacion']

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'consumos_incluidos', 'precio', 'activa']
    list_filter = ['activa']
    search_fields = ['nombre']

@admin.register(Asistente)
class AsistenteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'cc', 'categoria', 'ha_ingresado', 'consumos_disponibles', 'fecha_registro']
    list_filter = ['categoria', 'ha_ingresado', 'fecha_registro']
    search_fields = ['nombre', 'cc', 'correo']
    readonly_fields = ['codigo_qr', 'qr_image', 'fecha_registro']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('nombre', 'cc', 'numero', 'correo', 'categoria')
        }),
        ('Control de Ingreso', {
            'fields': ('ha_ingresado', 'fecha_ingreso', 'usuario_entrada')
        }),
        ('Consumos', {
            'fields': ('consumos_disponibles',)
        }),
        ('QR Code', {
            'fields': ('codigo_qr', 'qr_image')
        }),
        ('Metadatos', {
            'fields': ('fecha_registro', 'creado_por')
        })
    )

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'stock', 'stock_minimo', 'necesita_stock', 'activo']
    list_filter = ['activo', 'fecha_creacion']
    search_fields = ['nombre', 'descripcion']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion']
    
    def necesita_stock(self, obj):
        return obj.necesita_stock
    necesita_stock.boolean = True
    necesita_stock.short_description = 'Necesita Stock'

@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ['producto', 'tipo', 'cantidad', 'stock_anterior', 'stock_nuevo', 'fecha', 'usuario']
    list_filter = ['tipo', 'fecha', 'producto']
    search_fields = ['producto__nombre', 'observacion']
    readonly_fields = ['fecha', 'stock_anterior', 'stock_nuevo']

@admin.register(VentaBarra)
class VentaBarraAdmin(admin.ModelAdmin):
    list_display = ['producto', 'cantidad', 'asistente', 'total', 'usa_consumo_incluido', 'fecha', 'vendedor']
    list_filter = ['usa_consumo_incluido', 'fecha', 'producto']
    search_fields = ['producto__nombre', 'asistente__nombre']
    readonly_fields = ['total', 'fecha']

# Configurar el sitio admin
admin.site.site_header = "DMT 69 - Administración"
admin.site.site_title = "DMT 69 Admin"
admin.site.index_title = "Panel de Administración"