from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from functools import wraps


def rol_requerido(roles_permitidos):
    """
    Decorador que verifica si el usuario tiene uno de los roles permitidos
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Para peticiones AJAX devolver JSON
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"success": False, "message": "Usuario no autenticado"},
                        status=401,
                    )
                return redirect("login")

            try:
                perfil = request.user.perfilusuario
                # Admin siempre tiene acceso
                if perfil.rol == "admin" or perfil.rol in roles_permitidos:
                    return view_func(request, *args, **kwargs)
                else:
                    # Para peticiones AJAX devolver JSON
                    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                        return JsonResponse(
                            {
                                "success": False,
                                "message": "No tienes permisos para esta acción",
                            },
                            status=403,
                        )
                    messages.error(
                        request, "No tienes permisos para acceder a esta sección."
                    )
                    return redirect("core:dashboard")
            except Exception as e:
                # Para peticiones AJAX devolver JSON
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"success": False, "message": "Usuario sin rol asignado"},
                        status=403,
                    )
                messages.error(
                    request, "Usuario sin rol asignado. Contacta al administrador."
                )
                return redirect("core:dashboard")

        return _wrapped_view

    return decorator


def solo_entrada(view_func):
    """Solo personal de entrada"""
    return rol_requerido(["entrada"])(view_func)


def solo_barra(view_func):
    """Solo personal de barra"""
    return rol_requerido(["barra"])(view_func)


def entrada_o_admin(view_func):
    """Personal de entrada o admin"""
    return rol_requerido(["entrada", "admin"])(view_func)


def barra_o_admin(view_func):
    """Personal de barra o admin"""
    return rol_requerido(["barra", "admin"])(view_func)


def solo_admin(view_func):
    """Solo administradores"""
    return rol_requerido(["admin"])(view_func)


def ajax_login_required(view_func):
    """
    Decorador específico para vistas AJAX que requieren autenticación
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"success": False, "message": "Usuario no autenticado"}, status=401
            )
        return view_func(request, *args, **kwargs)

    return _wrapped_view
