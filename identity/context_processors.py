from types import SimpleNamespace

from branches.models import Branch, get_principal_branch
from identity.application import (
    build_permission_flags,
)


def _default_brand_branch():
    return SimpleNamespace(
        name="ZANN EVENT",
        primary_color="#1d3557",
        secondary_color="#e63946",
        page_background_color="#f4f1ea",
        surface_color="#fffdf8",
        panel_color="#efe7dc",
        logo=None,
    )


def get_brand_branch():
    return Branch.objects.filter(slug="sucursal-principal").first() or get_principal_branch()


def branch_context(request):
    brand_branch = getattr(request, "brand_branch", None) or get_brand_branch() or _default_brand_branch()
    current_branch = getattr(request, "current_branch", None)
    current_event = getattr(request, "current_event", None)
    theme_branch = current_branch or brand_branch
    permissions = getattr(request, "current_permissions", None) or build_permission_flags(
        getattr(request, "user", None),
        current_branch,
        current_event,
        role=getattr(request, "current_role", None),
    )
    return {
        "current_branch": current_branch,
        "current_event": current_event,
        "available_branches": getattr(request, "available_branches", []),
        "available_events": getattr(request, "available_events", []),
        "brand_branch": brand_branch,
        "theme_branch": theme_branch,
        "theme_branch_name": getattr(theme_branch, "name", "") or "ZANN EVENT",
        "sidebar_title": current_branch.name if current_branch else "Panel central",
        "current_event_label": current_event.name if current_event else "Sin evento",
        "brand_name": "ZANN EVENT",
        **permissions,
    }
