from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from events.application import get_event_choices
from events.forms import EventForm
from events.models import Event
from identity.application import get_user_events_for_branch, user_can_manage_branch, user_can_manage_events
from media_assets.application import resolve_field_file
from sales.application import ensure_event_product_defaults
from ticketing.application import build_qr_preview_data_uri, build_qr_preview_event


def _safe_asset(field_file):
    if not field_file:
        return {"url": "", "name": ""}
    try:
        return {"url": field_file.url, "name": field_file.name.rsplit("/", 1)[-1]}
    except ValueError:
        return {"url": "", "name": field_file.name.rsplit("/", 1)[-1] if getattr(field_file, "name", "") else ""}


def _event_asset(event, field_name, kind):
    return _safe_asset(resolve_field_file(event, field_name, kind))


def _event_form_context(form, title, branch):
    event = form.instance
    return {
        "form": form,
        "title": title,
        "branch": branch,
        "asset_preview": {
            "logo": _event_asset(event, "logo", "event_logo"),
            "qr_logo": _event_asset(event, "qr_logo", "event_qr_logo"),
            "flyer": _event_asset(event, "flyer", "event_flyer"),
        },
    }


@login_required
def event_list(request):
    branch = request.current_branch
    if not user_can_manage_events(request.user, branch, request.current_event):
        messages.error(request, "No tienes permisos para administrar eventos.")
        return redirect("shared_ui:dashboard")
    events = get_event_choices(branch) if user_can_manage_branch(request.user, branch) else get_user_events_for_branch(request.user, branch)
    return render(request, "events/list.html", {"events": events, "branch": branch})


@login_required
def event_create(request):
    branch = request.current_branch
    if not branch:
        messages.error(request, "Debes seleccionar una sucursal para crear eventos.")
        return redirect("shared_ui:dashboard")
    if not user_can_manage_events(request.user, branch, request.current_event):
        messages.error(request, "No tienes permisos para crear eventos en esta sucursal.")
        return redirect("shared_ui:dashboard")

    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.branch = branch
        event.save()
        ensure_event_product_defaults(branch=branch, event=event, user=request.user)
        messages.success(request, f"Evento {event.name} creado.")
        return redirect("events:update", event_id=event.id)

    return render(request, "events/form.html", _event_form_context(form, "Nuevo evento", branch))


@login_required
def event_update(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    branch = event.branch
    if not user_can_manage_events(request.user, branch, event):
        messages.error(request, "No tienes permisos para editar este evento.")
        return redirect("shared_ui:dashboard")

    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Evento {event.name} actualizado.")
        return redirect("events:update", event_id=event.id)

    return render(request, "events/form.html", _event_form_context(form, f"Editar {event.name}", branch))


@login_required
def qr_preview(request):
    branch = request.current_branch
    event = request.current_event
    if not branch or not user_can_manage_events(request.user, branch, event):
        return JsonResponse({"success": False, "message": "Sin permisos."}, status=403)
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Metodo no permitido."}, status=405)

    event_id = request.POST.get("event_id")
    source_event = Event(branch=branch)
    if event_id:
        source_event = get_object_or_404(Event, pk=event_id, branch=branch)
        if not user_can_manage_events(request.user, branch, source_event):
            return JsonResponse({"success": False, "message": "Sin permisos."}, status=403)

    preview_event = build_qr_preview_event(source_event, branch, files=request.FILES, data=request.POST)
    image = build_qr_preview_data_uri(
        request.POST.get("code") or "DMT-EVT-ABCD1234",
        preview_event,
        branch,
    )
    return JsonResponse({"success": True, "image": image})


@login_required
def switch_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.current_branch_id != event.branch_id:
        messages.error(request, "El evento no pertenece a la sucursal activa.")
        return redirect("shared_ui:dashboard")
    if not user_can_manage_branch(request.user, event.branch):
        allowed_event_ids = set(get_user_events_for_branch(request.user, event.branch).values_list("id", flat=True))
        if event.id not in allowed_event_ids:
            messages.error(request, "No puedes acceder a este evento.")
            return redirect("shared_ui:dashboard")

    request.session["current_event_id"] = event.id
    messages.success(request, f"Evento activo: {event.name}.")
    return redirect(request.META.get("HTTP_REFERER") or "shared_ui:dashboard")
