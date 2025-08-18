# core/urls_barra.py
from django.urls import path
from . import views_barra

app_name = "barra"

urlpatterns = [
    # Dashboard barra
    path("", views_barra.dashboard_barra, name="dashboard"),
    # Control de inventario
    path("inventario/", views_barra.inventario, name="inventario"),
    path("productos/", views_barra.lista_productos, name="lista_productos"),
    path("productos/crear/", views_barra.crear_producto, name="crear_producto"),
    path(
        "productos/<int:pk>/editar/",
        views_barra.editar_producto,
        name="editar_producto",
    ),
    path(
        "productos/<int:pk>/ajustar-stock/",
        views_barra.ajustar_stock,
        name="ajustar_stock",
    ),
    # Movimientos de stock
    path("movimientos/", views_barra.movimientos_stock, name="movimientos_stock"),
    path(
        "movimientos/registrar/",
        views_barra.registrar_movimiento,
        name="registrar_movimiento",
    ),
    # Control de ventas
    path("pos/", views_barra.pos_ventas, name="pos_ventas"),
    path("procesar-venta/", views_barra.procesar_venta, name="procesar_venta"),
    path("buscar-cliente/", views_barra.buscar_cliente_qr, name="buscar_cliente"),
    # Reportes de ventas
    path("ventas/", views_barra.lista_ventas, name="lista_ventas"),
    path("ventas/dia/", views_barra.ventas_del_dia, name="ventas_del_dia"),
    path("reportes/", views_barra.reportes_barra, name="reportes"),
    path("reporte-final/", views_barra.reporte_final, name="reporte_final"),
    # Exportar datos
    path(
        "exportar/inventario/",
        views_barra.exportar_inventario,
        name="exportar_inventario",
    ),
    path("exportar/ventas/", views_barra.exportar_ventas, name="exportar_ventas"),
    path(
        "exportar/movimientos/",
        views_barra.exportar_movimientos,
        name="exportar_movimientos",
    ),
]
