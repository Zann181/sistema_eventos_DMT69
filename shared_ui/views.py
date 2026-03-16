from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from shared_ui.application import build_dashboard_analytics, build_empty_dashboard_analytics


@method_decorator([never_cache, ensure_csrf_cookie], name="dispatch")
class BrandedLoginView(LoginView):
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        get_token(request)
        response = super().dispatch(request, *args, **kwargs)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


@never_cache
@ensure_csrf_cookie
def csrf_failure(request, reason="", template_name="registration/login.html"):
    get_token(request)
    response = render(
        request,
        template_name,
        {
            "form": None,
            "csrf_failure_message": (
                "Tu sesion o el formulario expiraron. Recarga la pagina e intenta iniciar sesion de nuevo."
            ),
            "csrf_failure_reason": reason,
        },
        status=403,
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def custom_logout(request):
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        messages.success(request, f"Sesion de {username} cerrada correctamente.")
    return redirect("login")

@login_required
def dashboard(request):
    branch = request.current_branch
    event = request.current_event

    metrics = {
        "attendees": 0,
        "checked_in": 0,
        "pending": 0,
        "products": 0,
        "sales_total": 0,
        "collected_total": Decimal("0"),
        "expense_total": Decimal("0"),
        "net_total": Decimal("0"),
    }

    analytics = build_dashboard_analytics(branch, event) if branch and event else build_empty_dashboard_analytics()

    if branch and event:
        entrance_metrics = analytics["entrada_analytics"]["metrics"]
        bar_metrics = analytics["barra_analytics"]["metrics"]
        dashboard_metrics = analytics["dashboard_summary"]["metrics"]
        metrics["attendees"] = entrance_metrics.get("attendees", 0)
        metrics["checked_in"] = entrance_metrics.get("checked_in", 0)
        metrics["pending"] = entrance_metrics.get("pending", 0)
        metrics["products"] = bar_metrics.get("total_products", 0)
        metrics["sales_total"] = bar_metrics.get("income_total", Decimal("0"))
        metrics["collected_total"] = dashboard_metrics.get("income_total", Decimal("0"))
        metrics["expense_total"] = dashboard_metrics.get("expense_total", Decimal("0"))
        metrics["net_total"] = dashboard_metrics.get("net_operating", Decimal("0"))

    branch_summary = []
    if branch:
        branch_summary = (
            branch.events.annotate(attendee_total=Count("attendees"), sales_total=Sum("sales__total"))
            .order_by("-starts_at")[:6]
        )

    return render(
        request,
        "shared_ui/dashboard.html",
        {
            "metrics": metrics,
            "branch_summary": branch_summary,
            "branch": branch,
            "event": event,
            **analytics,
        },
    )
