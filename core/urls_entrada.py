# core/urls_entrada.py
from django.urls import path
from . import views_entrada

app_name = 'entrada'

urlpatterns = [
    # Dashboard entrada
    path('', views_entrada.dashboard_entrada, name='dashboard'),
    
    # Gestión de asistentes
    path('asistentes/', views_entrada.lista_asistentes, name='lista_asistentes'),
    path('asistentes/crear/', views_entrada.crear_asistente, name='crear_asistente'),
    path('asistentes/<str:cc>/editar/', views_entrada.editar_asistente, name='editar_asistente'),
    path('asistentes/<str:cc>/qr/', views_entrada.ver_qr, name='ver_qr'),
    path('asistentes/<str:cc>/eliminar/', views_entrada.eliminar_asistente, name='eliminar_asistente'),
    
    # Generación de QR
    path('generar-qr/<str:cc>/', views_entrada.generar_qr, name='generar_qr'),
    path('descargar-qr/<str:cc>/', views_entrada.descargar_qr, name='descargar_qr'),
    
    # Scanner QR
    path('scanner/', views_entrada.scanner_qr, name='scanner_qr'),
    path('verificar-qr/', views_entrada.verificar_qr, name='verificar_qr'),
    
    # Búsqueda y filtros
    path('buscar/', views_entrada.buscar_asistente, name='buscar_asistente'),
    path('exportar/', views_entrada.exportar_excel, name='exportar_excel'),
    
    # Reportes
    path('reportes/', views_entrada.reportes_entrada, name='reportes'),
]