import json
import qrcode
from io import BytesIO
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.db import transaction
from django.core.files import File
from openpyxl import Workbook
from .models import Asistente, Categoria, PerfilUsuario
from .decorators import entrada_o_admin, solo_entrada, ajax_login_required


from decimal import Decimal, ROUND_HALF_UP
import uuid
from django.utils import timezone

from django.http import HttpResponse
from .models import Asistente

# ===== DASHBOARD ENTRADA =====


@entrada_o_admin
def dashboard_entrada(request):
    """Dashboard específico para personal de entrada"""
    hoy = datetime.now().date()

    stats = {
        "total_asistentes": Asistente.objects.count(),
        "asistentes_ingresados": Asistente.objects.filter(ha_ingresado=True).count(),
        "pendientes_ingreso": Asistente.objects.filter(ha_ingresado=False).count(),
        "mis_verificaciones": Asistente.objects.filter(
            usuario_entrada=request.user, ha_ingresado=True, fecha_ingreso__date=hoy
        ).count(),
        "verificaciones_hoy": Asistente.objects.filter(
            ha_ingresado=True, fecha_ingreso__date=hoy
        ).count(),
    }

    ultimos_ingresos = Asistente.objects.filter(
        usuario_entrada=request.user, ha_ingresado=True, fecha_ingreso__date=hoy
    ).order_by("-fecha_ingreso")[:5]

    stats_categorias = Categoria.objects.annotate(
        total_registrados=Count("asistente"),
        total_ingresados=Count("asistente", filter=Q(asistente__ha_ingresado=True)),
    ).filter(activa=True)

    categorias = Categoria.objects.filter(activa=True)  # <-- añadir

    context = {
        "stats": stats,
        "ultimos_ingresos": ultimos_ingresos,
        "stats_categorias": stats_categorias,
        "categorias": categorias,                      # <-- añadir
    }
    return render(request, "core/entrada/dashboard.html", context)


# ===== GESTIÓN DE ASISTENTES =====
# ===== GESTIÓN DE ASISTENTES =====
@entrada_o_admin
@require_http_methods(["POST"])
def registrar_evento_dia(request):
    """
    Registro masivo para el día del evento:
    - Divide el total pagado entre cantidad de asistentes -> precio_unitario
    - Asigna a una categoría especial "Día"
    - Crea asistentes genéricos marcados como ingresados
    - CHAMBONADA: guarda el precio_unitario (valor de boleta) en consumos_disponibles (en pesos)
    - Devuelve JSON para feedback inmediato en el front
    """
    try:
        cantidad = int(request.POST.get("cantidad", "0"))
        total_pagado = Decimal(request.POST.get("precio", "0"))

        if cantidad <= 0 or total_pagado <= 0:
            return JsonResponse({"success": False, "message": "Cantidad y precio deben ser mayores a 0."})

        # Precio por persona (total / cantidad)
        precio_unitario = total_pagado / cantidad

        # Buscar o crear categoría "Día"
        cat, _ = Categoria.objects.get_or_create(
            nombre="Día",
            defaults={
                "consumos_incluidos": 0,
                "precio": precio_unitario,
                "descripcion": "Categoría generada automáticamente para asistentes del día",
                "activa": True,
            }
        )
        # Mantener actualizado el precio de la categoría
        if cat.precio != precio_unitario:
            cat.precio = precio_unitario
            cat.save(update_fields=["precio"])

        ahora = timezone.now()
        nuevos = []

        # CHAMBONADA: saldo en pesos (redondeo al peso más cercano) para cada asistente
        saldo_pesos = int(precio_unitario.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        for i in range(1, cantidad + 1):
            cc_auto = f"EV{uuid.uuid4().hex[:10].upper()}"
            codigo_qr_text = uuid.uuid4().hex

            nuevos.append(Asistente(
                nombre=f"Asistente Día {i}",
                cc=cc_auto,
                numero="",
                correo=f"dia{i}@dmt69.local",
                categoria=cat,
                codigo_qr=codigo_qr_text,
                ha_ingresado=True,
                fecha_ingreso=ahora,
                usuario_entrada=request.user,
                # >>> AQUÍ LA CHAMBONADA: ponemos el valor de la boleta como consumo disponible
                consumos_disponibles=saldo_pesos,
                creado_por=request.user,
            ))

        Asistente.objects.bulk_create(nuevos, batch_size=500)

        return JsonResponse({
            "success": True,
            "message": (
                f"Se registraron {cantidad} asistentes del día. "
                f"Precio unitario {precio_unitario:.2f}; consumo disponible por asistente: ${saldo_pesos}."
            )
        })

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {str(e)}"})



@entrada_o_admin
def lista_asistentes(request):
    """Lista completa de asistentes con filtros y búsqueda"""
    asistentes = Asistente.objects.all().order_by("-fecha_registro")
    categorias = Categoria.objects.filter(activa=True)

    # Filtros
    buscar = request.GET.get("buscar", "").strip()
    if buscar:
        asistentes = asistentes.filter(
            Q(nombre__icontains=buscar)
            | Q(cc__icontains=buscar)
            | Q(correo__icontains=buscar)
            | Q(numero__icontains=buscar)
        )

    categoria_id = request.GET.get("categoria")
    if categoria_id:
        asistentes = asistentes.filter(categoria_id=categoria_id)

    estado = request.GET.get("estado")
    if estado == "ingresados":
        asistentes = asistentes.filter(ha_ingresado=True)
    elif estado == "pendientes":
        asistentes = asistentes.filter(ha_ingresado=False)

    # Paginación básica
    total = asistentes.count()

    context = {
        "asistentes": asistentes[:100],  # Limitar a 100 resultados
        "categorias": categorias,
        "total": total,
        "ingresados": asistentes.filter(ha_ingresado=True).count(),
        "pendientes": asistentes.filter(ha_ingresado=False).count(),
        "filtros": {"buscar": buscar, "categoria": categoria_id, "estado": estado},
    }

    return render(request, "core/entrada/lista_asistentes.html", context)


@entrada_o_admin
def crear_asistente(request):
    """Crear nuevo asistente con generación automática de QR"""
    if request.method == "POST":
        try:
            with transaction.atomic():
                # Validar que no exista la cédula
                cc = request.POST.get("cc", "").strip()
                if Asistente.objects.filter(cc=cc).exists():
                    messages.error(request, f"Ya existe un asistente con cédula {cc}")
                    categorias = Categoria.objects.filter(activa=True)
                    return render(
                        request,
                        "core/entrada/asistente_form.html",
                        {"categorias": categorias},
                    )

                # Crear asistente
                asistente = Asistente.objects.create(
                    nombre=request.POST["nombre"].strip(),
                    cc=cc,
                    numero=request.POST["numero"].strip(),
                    correo=request.POST["correo"].strip(),
                    categoria_id=request.POST["categoria"],
                    creado_por=request.user,
                )

                messages.success(
                    request,
                    f"Asistente {asistente.nombre} creado exitosamente. QR generado automáticamente.",
                )
                return redirect("entrada:ver_qr", cc=asistente.cc)

        except Exception as e:
            messages.error(request, f"Error al crear asistente: {e}")

    categorias = Categoria.objects.filter(activa=True)
    return render(
        request, "core/entrada/asistente_form.html", {"categorias": categorias}
    )


@entrada_o_admin
def editar_asistente(request, cc):
    """Editar datos de un asistente"""
    asistente = get_object_or_404(Asistente, cc=cc)

    if request.method == "POST":
        try:
            with transaction.atomic():
                asistente.nombre = request.POST["nombre"].strip()
                asistente.numero = request.POST["numero"].strip()
                asistente.correo = request.POST["correo"].strip()
                asistente.categoria_id = request.POST["categoria"]

                # Actualizar consumos si cambió la categoría
                categoria_anterior = asistente.consumos_disponibles
                asistente.consumos_disponibles = asistente.categoria.consumos_incluidos

                asistente.save()

                messages.success(
                    request, f"Asistente {asistente.nombre} actualizado exitosamente."
                )
                return redirect("entrada:lista_asistentes")

        except Exception as e:
            messages.error(request, f"Error al actualizar asistente: {e}")

    categorias = Categoria.objects.filter(activa=True)
    context = {"asistente": asistente, "categorias": categorias, "editando": True}
    return render(request, "core/entrada/asistente_form.html", context)


@entrada_o_admin
def eliminar_asistente(request, cc):
    """Eliminar un asistente (solo si no ha ingresado)"""
    asistente = get_object_or_404(Asistente, cc=cc)

    if asistente.ha_ingresado:
        messages.error(
            request, "No se puede eliminar un asistente que ya ha ingresado al evento."
        )
        return redirect("entrada:lista_asistentes")

    if request.method == "POST":
        nombre = asistente.nombre
        asistente.delete()
        messages.success(request, f"Asistente {nombre} eliminado exitosamente.")
        return redirect("entrada:lista_asistentes")

    return render(
        request, "core/entrada/confirmar_eliminar.html", {"asistente": asistente}
    )


# ===== GESTIÓN DE QR =====


@entrada_o_admin
def ver_qr(request, cc):
    """Ver el código QR de un asistente con todos sus datos"""
    asistente = get_object_or_404(Asistente, cc=cc)

    # Regenerar QR si no existe
    if not asistente.qr_image:
        asistente.generar_qr()

    context = {
        "asistente": asistente,
        "qr_url": asistente.qr_image.url if asistente.qr_image else None,
    }

    return render(request, "core/entrada/ver_qr.html", context)


@entrada_o_admin
def generar_qr(request, cc):
    """Regenerar código QR para un asistente"""
    asistente = get_object_or_404(Asistente, cc=cc)

    try:
        asistente.generar_qr()
        messages.success(request, f"Código QR regenerado para {asistente.nombre}")
    except Exception as e:
        messages.error(request, f"Error generando QR: {e}")

    return redirect("entrada:ver_qr", cc=cc)


@entrada_o_admin
def descargar_qr(request, cc):
    """Descargar imagen QR"""
    asistente = get_object_or_404(Asistente, cc=cc)

    if not asistente.qr_image:
        asistente.generar_qr()

    response = HttpResponse(asistente.qr_image.read(), content_type="image/png")
    response["Content-Disposition"] = (
        f'attachment; filename="qr_{asistente.cc}_{asistente.nombre}.png"'
    )
    return response


# ===== SCANNER QR =====


@solo_entrada
def scanner_qr(request):
    """Vista del scanner QR para verificar entrada"""
    hoy = datetime.now().date()

    context = {
        "mis_verificaciones": Asistente.objects.filter(
            usuario_entrada=request.user, ha_ingresado=True, fecha_ingreso__date=hoy
        ).count(),
        "total_ingresados": Asistente.objects.filter(ha_ingresado=True).count(),
        "total_pendientes": Asistente.objects.filter(ha_ingresado=False).count(),
    }

    return render(request, "core/entrada/scanner.html", context)


@require_http_methods(["POST"])
@ajax_login_required
@solo_entrada
def verificar_qr(request):
    """Verificar código QR y confirmar ingreso con todos los datos"""
    try:
        data = json.loads(request.body)
        codigo = data.get("codigo", "").strip()

        if not codigo:
            return JsonResponse({"success": False, "message": "Código QR vacío"})

        try:
            asistente = Asistente.objects.get(codigo_qr=codigo)
        except Asistente.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Código QR inválido o asistente no encontrado",
                }
            )

        # Verificar si ya ingresó
        if asistente.ha_ingresado:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ya ingresó anteriormente",
                    "asistente": {
                        "nombre": asistente.nombre,
                        "cc": asistente.cc,
                        "categoria": asistente.categoria.nombre,
                        "fecha_ingreso": asistente.fecha_ingreso.strftime(
                            "%d/%m/%Y %H:%M"
                        ),
                        "verificado_por": (
                            asistente.usuario_entrada.username
                            if asistente.usuario_entrada
                            else "N/A"
                        ),
                    },
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
                "message": "Acceso autorizado",
                "asistente": {
                    "nombre": asistente.nombre,
                    "cc": asistente.cc,
                    "numero": asistente.numero,
                    "correo": asistente.correo,
                    "categoria": asistente.categoria.nombre,
                    "consumos_disponibles": asistente.consumos_disponibles,
                    "precio_categoria": float(asistente.categoria.precio),
                    "fecha_registro": asistente.fecha_registro.strftime("%d/%m/%Y"),
                    "hora_ingreso": datetime.now().strftime("%H:%M"),
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Datos JSON inválidos"}, status=400
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error interno: {str(e)}"}, status=500
        )


# ===== BÚSQUEDA =====


@entrada_o_admin
def buscar_asistente(request):
    """Búsqueda específica de asistente por cédula"""
    cc = request.GET.get("cc", "").strip()

    if not cc:
        return JsonResponse({"success": False, "message": "Cédula requerida"})

    try:
        asistente = Asistente.objects.get(cc=cc)
        return JsonResponse(
            {
                "success": True,
                "asistente": {
                    "nombre": asistente.nombre,
                    "cc": asistente.cc,
                    "numero": asistente.numero,
                    "correo": asistente.correo,
                    "categoria": asistente.categoria.nombre,
                    "ha_ingresado": asistente.ha_ingresado,
                    "fecha_ingreso": (
                        asistente.fecha_ingreso.strftime("%d/%m/%Y %H:%M")
                        if asistente.fecha_ingreso
                        else None
                    ),
                    "consumos_disponibles": asistente.consumos_disponibles,
                    "qr_disponible": bool(asistente.qr_image),
                },
            }
        )
    except Asistente.DoesNotExist:
        return JsonResponse({"success": False, "message": "Asistente no encontrado"})


# ===== EXPORTAR =====


def exportar_excel(request):
    """
    Exportar lista de asistentes a Excel con las columnas específicas.
    Consumos Disponibles muestra el valor pagado individualmente (precio unitario)
    para los asistentes del día del evento (categoría "Día"). Al final se incluye
    una fila con el valor neto total de todas las entradas.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Asistentes DMT 69"

    # Cabeceras personalizadas
    headers = [
        "Nombre", "Cédula", "Teléfono", "Correo",
        "Categoría", "Consumos Disponibles",
        "Estado", "Verificado Por", "Valor entrada",
    ]
    ws.append(headers)

    total_neto = Decimal(0)
    asistentes_queryset = Asistente.objects.all().select_related("categoria", "usuario_entrada").order_by("categoria__nombre", "nombre")

    for asistente in asistentes_queryset:
        # Precio de entrada para cada asistente
        precio_entrada = asistente.categoria.precio
        total_neto += precio_entrada

        # “Consumos Disponibles”: mostrar precio individual si es categoría "Día"
        if asistente.categoria.nombre == "Día":
            consumo_disp = float(precio_entrada)  # precio unitario pagado
        else:
            consumo_disp = asistente.consumos_disponibles

        estado = "INGRESADO" if asistente.ha_ingresado else "PENDIENTE"
        verificado_por = asistente.usuario_entrada.username if asistente.usuario_entrada else ""

        ws.append([
            asistente.nombre,
            asistente.cc,
            asistente.numero,
            asistente.correo,
            asistente.categoria.nombre,
            consumo_disp,
            estado,
            verificado_por,
            float(precio_entrada),
        ])

    # Fila de valor neto total
    ws.append(["", "", "", "", "", "", "", "VALOR NETO", float(total_neto)])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename=asistentes_dmt69_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    wb.save(response)
    return response

# ===== REPORTES =====


@entrada_o_admin
def reportes_entrada(request):
    """Reportes y estadísticas de entrada"""
    hoy = datetime.now().date()

    # Estadísticas generales
    stats = {
        "total_registrados": Asistente.objects.count(),
        "total_ingresados": Asistente.objects.filter(ha_ingresado=True).count(),
        "ingresos_hoy": Asistente.objects.filter(fecha_ingreso__date=hoy).count(),
        "pendientes": Asistente.objects.filter(ha_ingresado=False).count(),
    }

    # Por categoría
    stats_categorias = Categoria.objects.annotate(
        registrados=Count("asistente"),
        ingresados=Count("asistente", filter=Q(asistente__ha_ingresado=True)),
        ingresos_hoy=Count("asistente", filter=Q(asistente__fecha_ingreso__date=hoy)),
    ).filter(activa=True)

    # Ingresos por hora (hoy)
    from django.db.models import Count
    from django.db.models.functions import Extract

    ingresos_por_hora = (
        Asistente.objects.filter(fecha_ingreso__date=hoy)
        .extra({"hora": "EXTRACT(hour FROM fecha_ingreso)"})
        .values("hora")
        .annotate(total=Count("cc"))
        .order_by("hora")
    )

    context = {
        "stats": stats,
        "stats_categorias": stats_categorias,
        "ingresos_por_hora": ingresos_por_hora,
        "fecha_reporte": hoy,
    }

    return render(request, "core/entrada/reportes.html", context)
