import json
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.db import transaction
from .models import Asistente, Categoria, PerfilUsuario
from .decorators import entrada_o_admin, solo_entrada, ajax_login_required

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


# ===== DASHBOARD PRINCIPAL =====
@login_required
def dashboard(request):
    try:
        perfil = request.user.perfilusuario
        if perfil.rol in ["entrada", "admin"]:
            return dashboard_entrada(request)
        elif perfil.rol == "barra":
            messages.info(request, "Dashboard de barra en construcción")
            return dashboard_entrada(request)  # Temporal
        else:
            messages.error(request, "Rol no reconocido")
            return redirect("admin:index")
    except PerfilUsuario.DoesNotExist:
        messages.error(request, "Usuario sin perfil. Contacta al administrador.")
        return redirect("admin:index")


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



# ===== CREAR ASISTENTE =====
@entrada_o_admin
def crear_asistente(request):
    if request.method == "POST":
        try:
            with transaction.atomic():
                cc = request.POST.get("cc", "").strip()
                if Asistente.objects.filter(cc=cc).exists():
                    messages.error(request, f"Ya existe asistente con cédula {cc}")
                else:
                    asistente = Asistente.objects.create(
                        nombre=request.POST["nombre"].strip(),
                        cc=cc,
                        numero=request.POST["numero"].strip(),
                        correo=request.POST["correo"].strip(),
                        categoria_id=request.POST["categoria"],
                        creado_por=request.user,
                    )
                    messages.success(
                        request, f"Asistente {asistente.nombre} creado exitosamente"
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
    

    