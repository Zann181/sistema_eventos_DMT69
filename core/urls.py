from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard principal
    path('', views.dashboard, name='dashboard'),
    
    # ÁREA ENTRADA
    path('asistentes/', views.lista_asistentes, name='lista_asistentes'),
    path('asistentes/crear/', views.crear_asistente, name='crear_asistente'),
    path('asistentes/<str:cc>/qr/', views.ver_qr, name='ver_qr'),
    path('asistentes/<str:cc>/editar/', views.editar_asistente, name='editar_asistente'),
    path('scanner/', views.scanner_qr, name='scanner_qr'),
    path('verificar-qr/', views.verificar_qr, name='verificar_qr'),
    path('buscar/', views.buscar_asistente, name='buscar_asistente'),
    
    # Nuevas funciones AJAX
    path('marcar-ingreso/', views.marcar_ingreso, name='marcar_ingreso'),
    path('eliminar-asistente/', views.eliminar_asistente, name='eliminar_asistente'),
    path('obtener-qr/<str:cc>/', views.obtener_qr, name='obtener_qr'),

     # URL NUEVA PARA CONSULTAR EL QR
    path('entrada/buscar-asistente-qr/', views.buscar_asistente_qr, name='buscar_asistente_qr'),
]