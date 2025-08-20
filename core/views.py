import json
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum
from django.db import transaction
from .models import Asistente, Categoria, PerfilUsuario
from .decorators import entrada_o_admin, solo_entrada, ajax_login_required

from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone


from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Importar modelos desde core
from core.models import Producto, VentaBarra, MovimientoStock, Asistente, PerfilUsuario
from core.decorators import ajax_login_required


    # Agregar estas importaciones al inicio del archivo views.py
from django.http import HttpResponse
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from datetime import datetime
import io


# ===== DASHBOARD PRINCIPAL CORREGIDO =====
@login_required
def dashboard(request):
    """Dashboard principal que redirige según el rol del usuario"""
    try:
        perfil = request.user.perfilusuario
        if perfil.rol in ["entrada", "admin"]:
            return dashboard_entrada(request)
        elif perfil.rol == "barra":
            # TEMPORAL: usar dashboard_entrada hasta que esté listo el módulo barra
            messages.info(request, "🍺 Sistema de barra en desarrollo. Usando dashboard temporal.")
            return redirect('core:dashboard_barra')
        else:
            messages.error(request, "Rol no reconocido")
            return redirect("admin:index")
    except PerfilUsuario.DoesNotExist:
        messages.error(request, "Usuario sin perfil. Contacta al administrador.")
        return redirect("admin:index")


def dashboard_barra_temporal(request):
    """Dashboard temporal para usuarios de barra usando funcionalidad existente"""
    hoy = datetime.now().date()

    # Importar modelos de barra si existen, sino usar valores por defecto
    try:
        from .models import Producto, VentaBarra, MovimientoStock
        
        # Estadísticas básicas de barra
        stats = {
            "total_productos": Producto.objects.filter(activo=True).count(),
            "productos_agotados": Producto.objects.filter(stock=0, activo=True).count(),
            "ventas_hoy": VentaBarra.objects.filter(
                vendedor=request.user, fecha__date=hoy
            ).count(),
            "ingresos_hoy": VentaBarra.objects.filter(
                vendedor=request.user, fecha__date=hoy
            ).aggregate(total=Sum('total'))['total'] or 0,
        }
        
        # Lista de productos para mostrar
        productos = []
        for producto in Producto.objects.filter(activo=True).order_by('nombre')[:12]:  # Máximo 12 productos
            # Color según stock
            if producto.stock == 0:
                color_stock = 'danger'
            elif producto.stock <= producto.stock_minimo:
                color_stock = 'warning'
            else:
                color_stock = 'success'
                
            productos.append({
                'producto': producto,
                'color_stock': color_stock,
                'puede_vender': producto.stock > 0
            })
        
        context = {
            "stats": stats,
            "productos": productos,
            "es_barra": True,
            "mensaje_desarrollo": "Sistema de barra en desarrollo - Vista temporal"
        }
        
    except ImportError:
        # Si no existen los modelos de barra, mostrar mensaje básico
        context = {
            "stats": {
                "total_productos": 0,
                "productos_agotados": 0,
                "ventas_hoy": 0,
                "ingresos_hoy": 0,
            },
            "productos": [],
            "es_barra": True,
            "mensaje_desarrollo": "Sistema de barra en desarrollo - Modelos no encontrados"
        }
    
    return render(request, "core/dashboard_barra_temporal.html", context)



def dashboard_entrada(request):
    hoy = datetime.now().date()

    # Estadísticas
    stats = {
        "total_asistentes": Asistente.objects.count(),
        "asistentes_ingresados": Asistente.objects.filter(ha_ingresado=True).count(),
        "pendientes": Asistente.objects.filter(ha_ingresado=False).count(),
        "mis_verificaciones": Asistente.objects.filter(
            usuario_entrada=request.user, fecha_ingreso__date=hoy
        ).count(),
    }

    # Categorías con stats
    categorias = Categoria.objects.annotate(
        total=Count("asistente"),
        ingresados=Count("asistente", filter=Q(asistente__ha_ingresado=True)),
    ).filter(activa=True)

    context = {"stats": stats, "categorias": categorias}
    return render(request, "core/dashboard_entrada.html", context)


# ===== LISTA ASISTENTES =====
# En core/views.py - Reemplaza la función lista_asistentes existente
@entrada_o_admin
def lista_asistentes(request):
    asistentes = Asistente.objects.all().order_by("-fecha_registro")

    # Filtros
    buscar = request.GET.get("buscar", "").strip()
    if buscar:
        asistentes = asistentes.filter(
            Q(nombre__icontains=buscar) | Q(cc__icontains=buscar)
        )

    estado = request.GET.get("estado")
    if estado == "ingresados":
        asistentes = asistentes.filter(ha_ingresado=True)
    elif estado == "pendientes":
        asistentes = asistentes.filter(ha_ingresado=False)

    # Paginación
    items_por_pagina = int(request.GET.get('items', 10))  # Por defecto 10
    if items_por_pagina not in [10, 25, 50, 100]:
        items_por_pagina = 10
        
    paginator = Paginator(asistentes, items_por_pagina)
    page = request.GET.get('page', 1)
    
    try:
        asistentes_paginados = paginator.page(page)
    except PageNotAnInteger:
        asistentes_paginados = paginator.page(1)
    except EmptyPage:
        asistentes_paginados = paginator.page(paginator.num_pages)

    # Si es una petición AJAX, devolver solo la tabla
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        context = {
            "asistentes": asistentes_paginados,  # Ahora es paginado
            "paginator": paginator,
            "page_obj": asistentes_paginados,
            "total": paginator.count,
            "showing_start": asistentes_paginados.start_index(),
            "showing_end": asistentes_paginados.end_index(),
        }
        return render(request, "core/tabla_asistentes.html", context)

    context = {
        "asistentes": asistentes_paginados,
        "paginator": paginator,
        "page_obj": asistentes_paginados,
        "total": paginator.count,
        "buscar": buscar,
        "estado": estado,
        "items_por_pagina": items_por_pagina,
    }
    return render(request, "core/lista_asistentes.html", context)



# Reemplazar la función crear_asistente en views.py

@entrada_o_admin
def crear_asistente(request):
    if request.method == "POST":
        try:
            with transaction.atomic():
                cc = request.POST.get("cc", "").strip()
                if Asistente.objects.filter(cc=cc).exists():
                    messages.error(request, f"Ya existe asistente con cédula {cc}")
                else:
                    # Crear asistente
                    asistente = Asistente.objects.create(
                        nombre=request.POST["nombre"].strip(),
                        cc=cc,
                        numero=request.POST["numero"].strip(),
                        correo=request.POST["correo"].strip(),
                        categoria_id=request.POST["categoria"],
                        creado_por=request.user,
                    )
                    
                    # Generar QR
                    if not asistente.qr_image:
                        asistente.generar_qr()
                    
                    # Enviar email
                    primer_nombre = asistente.nombre.split()[0]
                    email_enviado = False
                    
                    try:
                        from .email_utils import enviar_email_bienvenida
                        email_enviado = enviar_email_bienvenida(asistente)
                    except Exception as e:
                        print(f"Error enviando email: {e}")
                    
                    # Mostrar mensaje según resultado
                    if email_enviado:
                        messages.success(
                            request, 
                            f"✅ Asistente {asistente.nombre} creado exitosamente. "
                            f"Email de confirmación enviado a {asistente.correo}"
                        )
                    else:
                        messages.warning(
                            request, 
                            f"⚠️ Asistente {asistente.nombre} creado, pero no se pudo enviar el email. "
                            f"Verifica la configuración de correo en settings.py"
                        )
                    
                    return redirect("core:ver_qr", cc=asistente.cc)
                    
        except Exception as e:
            messages.error(request, f"Error al crear asistente: {e}")

    # Redirigir de vuelta al dashboard
    return redirect("core:dashboard")

# ===== EDITAR ASISTENTE =====
@entrada_o_admin
def editar_asistente(request, cc):
    asistente = get_object_or_404(Asistente, cc=cc)

    if request.method == "POST":
        try:
            with transaction.atomic():
                asistente.nombre = request.POST["nombre"].strip()
                asistente.numero = request.POST["numero"].strip()
                asistente.correo = request.POST["correo"].strip()
                asistente.categoria_id = request.POST["categoria"]
                # Actualizar consumos según nueva categoría
                asistente.consumos_disponibles = asistente.categoria.consumos_incluidos
                asistente.save()
                messages.success(request, f"Asistente {asistente.nombre} actualizado")
                return redirect("core:dashboard")
        except Exception as e:
            messages.error(request, f"Error: {e}")

    categorias = Categoria.objects.filter(activa=True)
    return render(
        request,
        "core/editar_asistente.html",
        {"asistente": asistente, "categorias": categorias},
    )


# ===== VER QR =====
@entrada_o_admin
def ver_qr(request, cc):
    asistente = get_object_or_404(Asistente, cc=cc)

    # Generar QR si no existe
    if not asistente.qr_image:
        asistente.generar_qr()

    return render(request, "core/ver_qr.html", {"asistente": asistente})


# ===== SCANNER QR =====
@solo_entrada
def scanner_qr(request):
    return render(request, "core/scanner.html")


@require_http_methods(["POST"])
@ajax_login_required
@solo_entrada
def verificar_qr(request):
    try:
        data = json.loads(request.body)
        codigo = data.get("codigo", "").strip()

        if not codigo:
            return JsonResponse({"success": False, "message": "Código QR vacío"})

        try:
            asistente = Asistente.objects.get(codigo_qr=codigo)
        except Asistente.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Código QR inválido o no encontrado"}
            )

        # Verificar si ya ingresó
        if asistente.ha_ingresado:
            return JsonResponse(
                {
                    "success": False,
                    "message": f'{asistente.nombre} ya ingresó el {asistente.fecha_ingreso.strftime("%d/%m %H:%M")} verificado por {asistente.usuario_entrada.username}',
                }
            )

        # Marcar como ingresado
        with transaction.atomic():
            asistente.ha_ingresado = True
            asistente.fecha_ingreso = datetime.now()
            asistente.usuario_entrada = request.user
            asistente.save()

        return JsonResponse(
            {
                "success": True,
                "message": "ACCESO AUTORIZADO",
                "asistente": {
                    "nombre": asistente.nombre,
                    "cc": asistente.cc,
                    "categoria": asistente.categoria.nombre,
                    "consumos": asistente.consumos_disponibles,
                    "hora": datetime.now().strftime("%H:%M"),
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Datos JSON inválidos"})
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error interno: {str(e)}"})


# ===== BÚSQUEDA POR CC =====
@entrada_o_admin
def buscar_asistente(request):
    cc = request.GET.get("cc", "").strip()

    if not cc:
        return JsonResponse({"success": False, "message": "Número de cédula requerido"})

    try:
        asistente = Asistente.objects.get(cc=cc)
        return JsonResponse(
            {
                "success": True,
                "asistente": {
                    "nombre": asistente.nombre,
                    "cc": asistente.cc,
                    "categoria": asistente.categoria.nombre,
                    "ha_ingresado": asistente.ha_ingresado,
                    "fecha_ingreso": (
                        asistente.fecha_ingreso.strftime("%d/%m/%Y %H:%M")
                        if asistente.fecha_ingreso
                        else None
                    ),
                    "consumos": asistente.consumos_disponibles,
                    "verificado_por": (
                        asistente.usuario_entrada.username
                        if asistente.usuario_entrada
                        else None
                    ),
                },
            }
        )
    except Asistente.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Asistente no encontrado con esa cédula"}
        )


# ===== MARCAR INGRESO MANUAL =====
@require_http_methods(["POST"])
@ajax_login_required
@entrada_o_admin
def marcar_ingreso(request):
    try:
        data = json.loads(request.body)
        cc = data.get("cc", "").strip()

        if not cc:
            return JsonResponse({"success": False, "message": "Cédula requerida"})

        try:
            asistente = Asistente.objects.get(cc=cc)
        except Asistente.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Asistente no encontrado"}
            )

        if asistente.ha_ingresado:
            return JsonResponse(
                {"success": False, "message": "El asistente ya había ingresado"}
            )

        # Marcar como ingresado
        with transaction.atomic():
            asistente.ha_ingresado = True
            asistente.fecha_ingreso = datetime.now()
            asistente.usuario_entrada = request.user
            asistente.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"{asistente.nombre} marcado como ingresado exitosamente",
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {str(e)}"})


# ===== ELIMINAR ASISTENTE =====
@require_http_methods(["POST"])
@ajax_login_required
@entrada_o_admin
def eliminar_asistente(request):
    try:
        data = json.loads(request.body)
        cc = data.get("cc", "").strip()

        if not cc:
            return JsonResponse({"success": False, "message": "Cédula requerida"})

        try:
            asistente = Asistente.objects.get(cc=cc)
        except Asistente.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Asistente no encontrado"}
            )

        if asistente.ha_ingresado:
            return JsonResponse(
                {
                    "success": False,
                    "message": "No se puede eliminar un asistente que ya ingresó",
                }
            )

        nombre = asistente.nombre
        asistente.delete()

        return JsonResponse(
            {"success": True, "message": f"{nombre} eliminado exitosamente"}
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {str(e)}"})


# ===== OBTENER QR =====
@entrada_o_admin
def obtener_qr(request, cc):
    try:
        asistente = Asistente.objects.get(cc=cc)
        if not asistente.qr_image:
            asistente.generar_qr()

        return JsonResponse(
            {
                "success": True,
                "qr_url": asistente.qr_image.url,
                "asistente": {
                    "nombre": asistente.nombre,
                    "cc": asistente.cc,
                    "categoria": asistente.categoria.nombre,
                    "consumos": asistente.consumos_disponibles,
                },
            }
        )
    except Asistente.DoesNotExist:
        return JsonResponse({"success": False, "message": "Asistente no encontrado"})


# VISTA PARA CONSULTAR QR (SIN GUARDAR NADA)
def buscar_asistente_qr(request):
    codigo_qr = request.GET.get("codigo_qr", None)
    if not codigo_qr:
        return JsonResponse({"success": False, "message": "Código QR no proporcionado"})

    try:
        asistente = Asistente.objects.get(codigo_qr=codigo_qr)

        if asistente.ha_ingresado:
            return JsonResponse(
                {
                    "success": False,
                    "message": f'{asistente.nombre} ya ingresó el {asistente.fecha_ingreso.strftime("%d/%m a las %H:%M")}',
                }
            )

        return JsonResponse(
            {
                "success": True,
                "asistente": {
                    "cc": asistente.cc,
                    "nombre": asistente.nombre,
                    "categoria": asistente.categoria.nombre,
                    "consumos_disponibles": asistente.consumos_disponibles,
                },
            }
        )
    except Asistente.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Asistente no encontrado o QR inválido"}
        )


# En core/views.py
# ...


@require_http_methods(["POST"])
# ... (tus decoradores)
def verificar_qr(request):
    try:
        data = json.loads(request.body)
        # AHORA BUSCA POR CÉDULA (CC) EN LUGAR DE CÓDIGO QR
        cc = data.get("cc", "").strip()

        if not cc:
            return JsonResponse(
                {"success": False, "message": "Cédula no proporcionada"}
            )

        asistente = Asistente.objects.get(cc=cc)

        # ... (el resto de tu lógica para marcar el ingreso sigue igual) ...
        asistente.ha_ingresado = True
        asistente.fecha_ingreso = datetime.now()
        asistente.usuario_entrada = request.user
        asistente.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Ingreso confirmado",
                "asistente": {"nombre": asistente.nombre},
            }
        )

    except Asistente.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Asistente no encontrado para confirmar"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error interno: {str(e)}"})




@require_http_methods(["POST"])
@ajax_login_required
@solo_entrada
def verificar_qr_preview(request):
    """Vista para obtener información del asistente sin marcar ingreso aún"""
    try:
        if request.content_type != 'application/json':
            return JsonResponse({'success': False, 'message': 'Tipo de contenido inválido'}, status=400)
        
        data = json.loads(request.body)
        codigo = data.get('codigo', '').strip()
        
        if not codigo:
            return JsonResponse({'success': False, 'message': 'Código QR vacío'})
        
        try:
            asistente = Asistente.objects.get(codigo_qr=codigo)
        except Asistente.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Código QR inválido o asistente no encontrado'})
        
        if asistente.ha_ingresado:
            return JsonResponse({
                'success': False,
                'message': 'Este asistente ya ingresó anteriormente',
                'asistente': {'nombre': asistente.nombre}
            })
        
        return JsonResponse({
            'success': True,
            'asistente': {
                'nombre': asistente.nombre,
                'cc': asistente.cc,
                'numero': asistente.numero,
                'correo': asistente.correo,
                'categoria': asistente.categoria.nombre,
                'consumos': asistente.consumos_disponibles,
                'fecha_registro': asistente.fecha_registro.strftime('%d/%m/%Y') if asistente.fecha_registro else None
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)


@require_http_methods(["POST"])
@ajax_login_required
@solo_entrada
def confirmar_ingreso(request):
    """Vista para confirmar el ingreso después de la verificación"""
    try:
        if request.content_type != 'application/json':
            return JsonResponse({'success': False, 'message': 'Tipo de contenido inválido'}, status=400)
        
        data = json.loads(request.body)
        codigo = data.get('codigo', '').strip()
        
        if not codigo:
            return JsonResponse({'success': False, 'message': 'Código QR vacío'})
        
        try:
            asistente = Asistente.objects.get(codigo_qr=codigo)
        except Asistente.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Asistente no encontrado'})
        
        if asistente.ha_ingresado:
            return JsonResponse({'success': False, 'message': 'Ya ingresó anteriormente'})
        
        from django.utils import timezone
        fecha_ingreso = timezone.now()
        
        asistente.ha_ingresado = True
        asistente.fecha_ingreso = fecha_ingreso
        asistente.usuario_entrada = request.user
        asistente.save()
        
        return JsonResponse({
            'success': True,
            'asistente': {
                'nombre': asistente.nombre,
                'cc': asistente.cc,
                'categoria': asistente.categoria.nombre,
                'consumos': asistente.consumos_disponibles,
                'hora': fecha_ingreso.strftime('%H:%M:%S'),
                'fecha': fecha_ingreso.strftime('%d/%m/%Y')
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)
    

# Corrige la vista exportar_excel en views.py
@entrada_o_admin
def exportar_excel(request):
    """Exportar todos los asistentes a un archivo Excel"""
    try:
        # Obtener todos los asistentes
        asistentes = Asistente.objects.all().order_by('-fecha_registro')
        
        # Crear workbook y worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Asistentes DMT 69"
        
        # Configurar estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        center_alignment = Alignment(horizontal="center", vertical="center")
        
        # Definir headers
        headers = [
            'NOMBRE', 'CEDULA', 'TELEFONO', 'CORREO', 'CATEGORIA', 
            'CONSUMOS DISPONIBLES', 'ESTADO', 'FECHA REGISTRO', 
            'FECHA INGRESO', 'HORA INGRESO', 'VERIFICADO POR'
        ]
        
        # Escribir headers
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
        
        # Escribir datos de asistentes
        for row_num, asistente in enumerate(asistentes, 2):
            ws.cell(row=row_num, column=1, value=asistente.nombre)
            ws.cell(row=row_num, column=2, value=asistente.cc)
            ws.cell(row=row_num, column=3, value=asistente.numero or '')
            ws.cell(row=row_num, column=4, value=asistente.correo or '')
            ws.cell(row=row_num, column=5, value=asistente.categoria.nombre)
            ws.cell(row=row_num, column=6, value=asistente.consumos_disponibles)
            ws.cell(row=row_num, column=7, value="INGRESO" if asistente.ha_ingresado else "PENDIENTE")  # Corregido el texto
            
            # Fecha de registro
            if asistente.fecha_registro:
                ws.cell(row=row_num, column=8, value=asistente.fecha_registro.strftime('%d/%m/%Y'))
            else:
                ws.cell(row=row_num, column=8, value='')
            
            # Fecha y hora de ingreso
            if asistente.fecha_ingreso:
                ws.cell(row=row_num, column=9, value=asistente.fecha_ingreso.strftime('%d/%m/%Y'))
                ws.cell(row=row_num, column=10, value=asistente.fecha_ingreso.strftime('%H:%M:%S'))
            else:
                ws.cell(row=row_num, column=9, value='')
                ws.cell(row=row_num, column=10, value='')
            
            # Usuario que verificó
            if asistente.usuario_entrada:
                ws.cell(row=row_num, column=11, value=asistente.usuario_entrada.username)
            else:
                ws.cell(row=row_num, column=11, value='')
        
        # Ajustar ancho de columnas
        column_widths = {
            'A': 25,  # NOMBRE
            'B': 15,  # CEDULA
            'C': 15,  # TELEFONO
            'D': 30,  # CORREO
            'E': 20,  # CATEGORIA
            'F': 12,  # CONSUMOS
            'G': 12,  # ESTADO
            'H': 15,  # FECHA REGISTRO
            'I': 15,  # FECHA INGRESO
            'J': 12,  # HORA INGRESO
            'K': 15,  # VERIFICADO POR
        }
        
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width
        
        # Agregar información adicional al final
        total_row = len(asistentes) + 3
        ws.cell(row=total_row, column=1, value="RESUMEN:")
        ws.cell(row=total_row, column=1).font = Font(bold=True)
        
        ws.cell(row=total_row + 1, column=1, value=f"Total asistentes: {asistentes.count()}")
        ws.cell(row=total_row + 2, column=1, value=f"Han ingresado: {asistentes.filter(ha_ingresado=True).count()}")
        ws.cell(row=total_row + 3, column=1, value=f"Pendientes: {asistentes.filter(ha_ingresado=False).count()}")
        ws.cell(row=total_row + 4, column=1, value=f"Exportado el: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        ws.cell(row=total_row + 5, column=1, value=f"Exportado por: {request.user.username}")
        
        # Crear respuesta HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        filename = f"asistentes_dmt69_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Guardar workbook en response
        wb.save(response)
        
        return response
        
    except Exception as e:
        # En caso de error, devolver respuesta de error
        return JsonResponse({
            'success': False, 
            'message': f'Error al generar Excel: {str(e)}'
        }, status=500)

@entrada_o_admin
def exportar_excel_simple(request):
    """Versión simple para testing"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="asistentes.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Nombre', 'Cedula', 'Telefono', 'Email', 'Categoria', 'Estado'])
    
    asistentes = Asistente.objects.all()
    for asistente in asistentes:
        writer.writerow([
            asistente.nombre,
            asistente.cc,
            asistente.numero,
            asistente.correo,
            asistente.categoria.nombre,
            'INGRESÓ' if asistente.ha_ingresado else 'PENDIENTE'
        ])
    
    return response




# --------- Barras y ventas -------
# AGREGAR ESTAS FUNCIONES AL FINAL DE core/views.py

# REEMPLAZA ESTAS FUNCIONES EN TU core/views.py

# ===== SISTEMA DE BARRA =====

@login_required
def dashboard_barra(request):
    """Dashboard del sistema de barra"""
    try:
        perfil = request.user.perfilusuario
        if perfil.rol not in ['barra', 'admin']:
            messages.error(request, 'No tienes permisos para acceder al sistema de barra')
            return redirect('core:dashboard')
    except PerfilUsuario.DoesNotExist:
        messages.error(request, 'Usuario sin perfil asignado')
        return redirect('admin:index')
    
    hoy = datetime.now().date()
    
    # Estadísticas
    stats = {
        'productos_activos': Producto.objects.filter(activo=True, stock__gt=0).count(),
        'productos_agotados': Producto.objects.filter(activo=True, stock=0).count(),
        'mis_ventas_hoy': VentaBarra.objects.filter(
            vendedor=request.user, 
            fecha__date=hoy
        ).count(),
        'total_vendido_hoy': VentaBarra.objects.filter(
            vendedor=request.user, 
            fecha__date=hoy
        ).aggregate(total=Sum('total'))['total'] or 0
    }
    
    # Lista de productos con información de stock
    productos_info = []
    productos = Producto.objects.filter(activo=True).order_by('nombre')
    
    for producto in productos:
        # Determinar color del stock
        if producto.stock == 0:
            color_stock = 'danger'
        elif producto.stock <= producto.stock_minimo:
            color_stock = 'warning'
        else:
            color_stock = 'success'
        
        productos_info.append({
            'producto': producto,
            'color_stock': color_stock,
            'puede_vender': producto.stock > 0
        })
    
    context = {
        'stats': stats,
        'productos': productos_info,
        'user': request.user
    }
    
    return render(request, 'core/dashboard_barra.html', context)


# REEMPLAZA LA FUNCIÓN vender_producto EN core/views.py

@require_http_methods(["POST"])
@csrf_exempt
@ajax_login_required
def vender_producto(request):
    """Procesar venta de un producto - CORREGIDO CON COMPENSACIÓN +1"""
    try:
        perfil = request.user.perfilusuario
        if perfil.rol not in ['barra', 'admin']:
            return JsonResponse({'success': False, 'message': 'Sin permisos de barra'})
    except PerfilUsuario.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Usuario sin perfil'})
    
    try:
        data = json.loads(request.body)
        producto_id = data.get('producto_id')
        cantidad = 1  # SIEMPRE 1 para evitar problemas
        
        if not producto_id:
            return JsonResponse({'success': False, 'message': 'ID de producto requerido'})
        
        # Obtener producto con bloqueo
        try:
            with transaction.atomic():
                producto = Producto.objects.select_for_update().get(id=producto_id, activo=True)
                
                # Verificar stock ANTES de la venta
                if producto.stock < cantidad:
                    return JsonResponse({
                        'success': False, 
                        'message': f'Stock insuficiente. Disponible: {producto.stock}'
                    })
                
                # Guardar stock original para referencia
                stock_original = producto.stock
                
                # Crear la venta (esto va a descontar automáticamente el stock)
                venta = VentaBarra.objects.create(
                    asistente=None,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=producto.precio,
                    usa_consumo_incluido=False,
                    vendedor=request.user
                )
                
                # COMPENSACIÓN: Agregar +1 al stock para anular el doble descuento
                producto.refresh_from_db()  # Obtener el stock actualizado
                producto.stock += 1  # Compensar el doble descuento
                producto.save(update_fields=['stock'])
                
                # Verificar que el stock final sea correcto (original - 1)
                producto.refresh_from_db()
                stock_esperado = stock_original - cantidad
                
                if producto.stock != stock_esperado:
                    # Si aún no está correcto, forzar el stock correcto
                    producto.stock = stock_esperado
                    producto.save(update_fields=['stock'])
                
                # Determinar color del nuevo stock
                if producto.stock == 0:
                    nuevo_color_stock = 'danger'
                elif producto.stock <= producto.stock_minimo:
                    nuevo_color_stock = 'warning'
                else:
                    nuevo_color_stock = 'success'
                
                return JsonResponse({
                    'success': True,
                    'message': f'Venta de {producto.nombre} exitosa',
                    'venta': {
                        'id': venta.id,
                        'producto_nombre': producto.nombre,
                        'cantidad': cantidad,
                        'total': float(venta.total),
                        'nuevo_stock': producto.stock,
                        'color_stock': nuevo_color_stock,
                        'puede_vender': producto.stock > 0,
                        'cliente': 'Cliente General',
                        'hora': venta.fecha.strftime('%H:%M:%S')
                    }
                })
                
        except Producto.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Producto no encontrado'})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Formato JSON inválido'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

# OPCIONAL: Función de DEBUG para verificar stock después de ventas
@login_required
def debug_stock(request, producto_id):
    """Función temporal para verificar el stock de un producto"""
    try:
        producto = Producto.objects.get(id=producto_id)
        return JsonResponse({
            'producto': producto.nombre,
            'stock_actual': producto.stock,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    except Producto.DoesNotExist:
        return JsonResponse({'error': 'Producto no encontrado'})

@ajax_login_required
def obtener_stats_barra(request):
    """Obtener estadísticas actualizadas para el dashboard"""
    try:
        hoy = datetime.now().date()
        
        stats = {
            'productos_activos': Producto.objects.filter(activo=True, stock__gt=0).count(),
            'productos_agotados': Producto.objects.filter(activo=True, stock=0).count(),
            'mis_ventas_hoy': VentaBarra.objects.filter(
                vendedor=request.user, 
                fecha__date=hoy
            ).count(),
            'total_vendido_hoy': float(VentaBarra.objects.filter(
                vendedor=request.user, 
                fecha__date=hoy
            ).aggregate(total=Sum('total'))['total'] or 0)
        }
        
        return JsonResponse({'success': True, 'stats': stats})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@ajax_login_required
def buscar_asistente_barra(request):
    """Buscar asistente por cédula para la venta"""
    cc = request.GET.get('cc', '').strip()
    
    if not cc:
        return JsonResponse({'success': False, 'message': 'Cédula requerida'})
    
    try:
        asistente = Asistente.objects.get(cc=cc)
        
        if not asistente.ha_ingresado:
            return JsonResponse({
                'success': False,
                'message': f'{asistente.nombre} no ha ingresado al evento'
            })
        
        return JsonResponse({
            'success': True,
            'asistente': {
                'nombre': asistente.nombre,
                'cc': asistente.cc,
                'categoria': asistente.categoria.nombre,
                'consumos_disponibles': asistente.consumos_disponibles,
                'puede_usar_consumo': asistente.consumos_disponibles > 0
            }
        })
        
    except Asistente.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Asistente no encontrado'})


@login_required
def mis_ventas_barra(request):
    """Ver mis ventas del día"""
    try:
        perfil = request.user.perfilusuario
        if perfil.rol not in ['barra', 'admin']:
            messages.error(request, 'No tienes permisos para ver ventas')
            return redirect('core:dashboard')
    except PerfilUsuario.DoesNotExist:
        messages.error(request, 'Usuario sin perfil asignado')
        return redirect('admin:index')
    
    fecha = request.GET.get('fecha')
    if fecha:
        try:
            fecha_filtro = datetime.strptime(fecha, '%Y-%m-%d').date()
        except ValueError:
            fecha_filtro = datetime.now().date()
    else:
        fecha_filtro = datetime.now().date()
    
    # Obtener ventas del día
    ventas = VentaBarra.objects.filter(
        vendedor=request.user,
        fecha__date=fecha_filtro
    ).order_by('-fecha').select_related('producto', 'asistente')
    
    # Estadísticas del día
    stats_ventas = {
        'total_ventas': ventas.count(),
        'productos_vendidos': ventas.aggregate(total=Sum('cantidad'))['total'] or 0,
        'total_ingresos': ventas.aggregate(total=Sum('total'))['total'] or 0
    }
    
    context = {
        'ventas': ventas,
        'stats_ventas': stats_ventas,
        'fecha': fecha_filtro,
        'user': request.user
    }
    
    return render(request, 'core/mis_ventas_barra.html', context)


@login_required
def exportar_reporte_barra(request):
    """Exportar reporte de ventas a Excel"""
    try:
        perfil = request.user.perfilusuario
        if perfil.rol not in ['barra', 'admin']:
            messages.error(request, 'No tienes permisos')
            return redirect('core:dashboard')
    except PerfilUsuario.DoesNotExist:
        messages.error(request, 'Usuario sin perfil')
        return redirect('admin:index')
    
    try:
        hoy = datetime.now().date()
        
        # Obtener ventas del día
        ventas = VentaBarra.objects.filter(
            vendedor=request.user,
            fecha__date=hoy
        ).order_by('-fecha').select_related('producto', 'asistente')
        
        # Crear workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Ventas {request.user.username}"
        
        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
        center_alignment = Alignment(horizontal="center", vertical="center")
        
        # Headers
        headers = ['HORA', 'PRODUCTO', 'CANTIDAD', 'PRECIO UNIT.', 'TOTAL', 'CLIENTE']
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
        
        # Datos
        for row_num, venta in enumerate(ventas, 2):
            ws.cell(row=row_num, column=1, value=venta.fecha.strftime('%H:%M:%S'))
            ws.cell(row=row_num, column=2, value=venta.producto.nombre)
            ws.cell(row=row_num, column=3, value=venta.cantidad)
            ws.cell(row=row_num, column=4, value=float(venta.precio_unitario))
            ws.cell(row=row_num, column=5, value=float(venta.total))
            ws.cell(row=row_num, column=6, value=venta.asistente.nombre if venta.asistente else "Cliente General")
        
        # Ajustar columnas
        column_widths = [15, 25, 10, 15, 15, 25]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width
        
        # Totales
        total_row = len(ventas) + 3
        ws.cell(row=total_row, column=1, value="TOTALES:")
        ws.cell(row=total_row, column=1).font = Font(bold=True)
        
        total_productos = ventas.aggregate(total=Sum('cantidad'))['total'] or 0
        total_ingresos = ventas.aggregate(total=Sum('total'))['total'] or 0
        
        ws.cell(row=total_row, column=3, value=total_productos)
        ws.cell(row=total_row, column=5, value=float(total_ingresos))
        
        # Información adicional
        ws.cell(row=total_row + 2, column=1, value=f"Fecha: {hoy.strftime('%d/%m/%Y')}")
        ws.cell(row=total_row + 3, column=1, value=f"Vendedor: {request.user.username}")
        ws.cell(row=total_row + 4, column=1, value=f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Respuesta HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"ventas_{request.user.username}_{hoy.strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response
        
    except Exception as e:
        messages.error(request, f'Error generando reporte: {str(e)}')
        return redirect('core:mis_ventas_barra')