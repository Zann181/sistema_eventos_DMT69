from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Dashboard principal
    path("", views.dashboard, name="dashboard"),
    # ÁREA ENTRADA
    path("asistentes/", views.lista_asistentes, name="lista_asistentes"),
    path("asistentes/crear/", views.crear_asistente, name="crear_asistente"),
    path("asistentes/<str:cc>/qr/", views.ver_qr, name="ver_qr"),
    path(
        "asistentes/<str:cc>/editar/", views.editar_asistente, name="editar_asistente"
    ),
    path("scanner/", views.scanner_qr, name="scanner_qr"),
    path("verificar-qr/", views.verificar_qr, name="verificar_qr"),
    path("buscar/", views.buscar_asistente, name="buscar_asistente"),
    # Nuevas funciones AJAX
    path("marcar-ingreso/", views.marcar_ingreso, name="marcar_ingreso"),
    path("eliminar-asistente/", views.eliminar_asistente, name="eliminar_asistente"),
    path("obtener-qr/<str:cc>/", views.obtener_qr, name="obtener_qr"),
    # URL NUEVA PARA CONSULTAR EL QR
    path(
        "entrada/buscar-asistente-qr/",
        views.buscar_asistente_qr,
        name="buscar_asistente_qr",
    ),

    path('entrada/verificar-qr/', views.verificar_qr, name='verificar_qr'),
    
    # AGREGAR ESTAS DOS LÍNEAS:
    path('entrada/verificar-qr-preview/', views.verificar_qr_preview, name='verificar_qr_preview'),
    path('entrada/confirmar-ingreso/', views.confirmar_ingreso, name='confirmar_ingreso'),
    # Agregar esta línea en tu archivo urls.py dentro de urlpatterns
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),
    path('exportar-csv/', views.exportar_excel_simple, name='exportar_csv'),

    # ===== ÃREA BARRA =====
    path("barra/", views.dashboard_barra, name="dashboard_barra"),
    path("barra/vender/", views.vender_producto, name="vender_producto"),
    path("barra/stats/", views.obtener_stats_barra, name="obtener_stats_barra"),
    path("barra/buscar-asistente/", views.buscar_asistente_barra, name="buscar_asistente_barra"),
    path("barra/mis-ventas/", views.mis_ventas_barra, name="mis_ventas_barra"),
    path("barra/exportar-reporte/", views.exportar_reporte_barra, name="exportar_reporte_barra"),

    # ===== FUNCIONES AUXILIARES PARA SISTEMA DE BARRA =====
    path("barra/actualizar-stock-inicial/", views.actualizar_stock_inicial_dia, name="actualizar_stock_inicial_dia"),
    path("barra/debug-ventas/", views.debug_ventas_calculadas, name="debug_ventas_calculadas"),

]
