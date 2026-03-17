from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from catalog.forms import ProductForm
from catalog.models import Product
from identity.application import user_can_access_catalog, user_can_manage_events
from sales.models import EventProduct


@login_required
def product_list(request):
    branch = request.current_branch
    event = request.current_event
    if not user_can_access_catalog(request.user, branch, event):
        messages.error(request, "No tienes permisos para acceder al catalogo.")
        return redirect("shared_ui:dashboard")

    products = Product.objects.order_by("name")
    event_configs = {}
    if branch and event:
        event_configs = {
            config.product_id: config
            for config in EventProduct.objects.filter(branch=branch, event=event).select_related("product")
        }
    product_rows = []
    for product in products:
        config = event_configs.get(product.id)
        product_rows.append(
            {
                "product": product,
                "config": config,
                "is_enabled": config.is_enabled if config else False,
                "event_price": config.normalized_event_price() if config else None,
            }
        )
    form = ProductForm()
    return render(
        request,
        "catalog/list.html",
        {
            "products": products,
            "product_rows": product_rows,
            "form": form,
            "branch": branch,
            "event": event,
            "can_configure_event_products": bool(branch and event and user_can_manage_events(request.user, branch, event)),
        },
    )


@login_required
def product_create(request):
    branch = request.current_branch
    event = request.current_event
    if not branch or not event:
        messages.error(request, "Selecciona una sucursal y un evento para crear el producto.")
        return redirect("shared_ui:dashboard")
    if not user_can_manage_events(request.user, branch, event):
        messages.error(request, "No tienes permisos para crear productos en este evento.")
        return redirect("shared_ui:dashboard")

    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.branch = branch
        product.created_by = request.user
        product.save()
        EventProduct.objects.get_or_create(
            branch=branch,
            event=event,
            product=product,
            defaults={
                "is_enabled": False,
                "event_price": None,
                "updated_by": request.user,
            },
        )
        messages.success(request, f"Producto global {product.name} creado. Configura el precio del evento para habilitarlo.")
        return redirect(f"{reverse('sales:pos')}?action=evento-productos")

    return render(
        request,
        "catalog/form.html",
        {
            "form": form,
            "branch": branch,
            "event": event,
            "title": "Nuevo producto",
        },
    )
