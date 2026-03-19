from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from attendees.application import delete_branch_category
from attendees.forms import BranchCategoryForm
from attendees.models import Category
from catalog.forms import ProductForm
from catalog.models import Product
from identity.application import user_can_access_catalog, user_can_manage_categories, user_can_manage_events
from sales.application import retire_product
from sales.models import EventProduct


def _build_catalog_context(
    request,
    branch,
    event,
    *,
    category_form=None,
    editing_category=None,
    product_form=None,
    editing_product=None,
):
    products = Product.objects.filter(branch=branch).order_by("name") if branch else Product.objects.none()
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
    return {
        "products": products,
        "product_rows": product_rows,
        "product_form": product_form or ProductForm(instance=editing_product),
        "category_form": category_form or BranchCategoryForm(branch=branch, instance=editing_category),
        "editing_category": editing_category,
        "editing_product": editing_product,
        "branch_categories": branch.categories.order_by("name") if branch else Category.objects.none(),
        "branch": branch,
        "event": event,
        "can_configure_event_products": bool(branch and event and user_can_manage_events(request.user, branch, event)),
    }


def _catalog_categories_redirect():
    return f"{reverse('catalog:list')}#categorias-sucursal"


def _catalog_products_redirect():
    return f"{reverse('catalog:list')}#productos-globales"


def _catalog_categories_guard(request, branch, event):
    if not branch or not event:
        messages.error(request, "Selecciona una sucursal y un evento para administrar categorias.")
        return False
    if user_can_manage_categories(request.user, branch, event):
        return True
    messages.error(request, "Solo los administradores pueden gestionar categorias.")
    return False


def _catalog_products_guard(request, branch, event):
    if not branch or not event:
        messages.error(request, "Selecciona una sucursal y un evento para administrar productos.")
        return False
    if user_can_manage_events(request.user, branch, event):
        return True
    messages.error(request, "Solo los administradores pueden gestionar productos.")
    return False


@login_required
def product_list(request):
    branch = request.current_branch
    event = request.current_event
    if not user_can_access_catalog(request.user, branch, event):
        messages.error(request, "No tienes permisos para acceder al catalogo.")
        return redirect("shared_ui:dashboard")

    editing_category = None
    editing_product = None
    if branch and user_can_manage_categories(request.user, branch, event):
        editing_category = branch.categories.filter(pk=request.GET.get("edit_category")).first() if request.GET.get("edit_category") else None
    if branch and user_can_manage_events(request.user, branch, event):
        editing_product = (
            Product.objects.filter(branch=branch, pk=request.GET.get("edit_product")).first()
            if request.GET.get("edit_product")
            else None
        )

    return render(
        request,
        "catalog/list.html",
        _build_catalog_context(
            request,
            branch,
            event,
            editing_category=editing_category,
            editing_product=editing_product,
        ),
    )


@login_required
def product_create(request):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_products_guard(request, branch, event):
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
        return redirect(_catalog_products_redirect())

    return render(
        request,
        "catalog/list.html",
        _build_catalog_context(request, branch, event, product_form=form),
        status=400,
    )


@require_POST
@login_required
def product_update(request, product_id):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_products_guard(request, branch, event):
        return redirect("shared_ui:dashboard")

    product = get_object_or_404(Product, pk=product_id, branch=branch)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if form.is_valid():
        updated_product = form.save()
        messages.success(request, f"Producto {updated_product.name} actualizado.")
        return redirect(_catalog_products_redirect())

    messages.error(request, "Corrige los datos del producto.")
    return render(
        request,
        "catalog/list.html",
        _build_catalog_context(request, branch, event, product_form=form, editing_product=product),
        status=400,
    )


@require_POST
@login_required
def product_delete(request, product_id):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_products_guard(request, branch, event):
        return redirect("shared_ui:dashboard")

    product = get_object_or_404(Product, pk=product_id, branch=branch)
    result = retire_product(branch=branch, product=product, user=request.user)
    if result["mode"] == "retired":
        messages.success(
            request,
            f"Producto {product.name} retirado globalmente. Se desactivo para conservar el historial.",
        )
    else:
        messages.success(request, f"Producto {product.name} eliminado.")
    return redirect(_catalog_products_redirect())


@require_POST
@login_required
def category_create(request):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_categories_guard(request, branch, event):
        return redirect("shared_ui:dashboard")

    form = BranchCategoryForm(request.POST or None, branch=branch)
    if form.is_valid():
        category = form.save()
        messages.success(request, f"Categoria {category.name} creada para {branch.name}.")
        return redirect(_catalog_categories_redirect())

    messages.error(request, "Corrige los datos de la categoria.")
    return render(
        request,
        "catalog/list.html",
        _build_catalog_context(request, branch, event, category_form=form),
        status=400,
    )


@require_POST
@login_required
def category_update(request, category_id):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_categories_guard(request, branch, event):
        return redirect("shared_ui:dashboard")

    category = get_object_or_404(Category, pk=category_id, branch=branch)
    form = BranchCategoryForm(request.POST or None, branch=branch, instance=category)
    if form.is_valid():
        updated_category = form.save()
        messages.success(request, f"Categoria {updated_category.name} actualizada.")
        return redirect(_catalog_categories_redirect())

    messages.error(request, "Corrige los datos de la categoria.")
    return render(
        request,
        "catalog/list.html",
        _build_catalog_context(request, branch, event, category_form=form, editing_category=category),
        status=400,
    )


@require_POST
@login_required
def category_delete(request, category_id):
    branch = request.current_branch
    event = request.current_event
    if not _catalog_categories_guard(request, branch, event):
        return redirect("shared_ui:dashboard")

    category = get_object_or_404(Category, pk=category_id, branch=branch)
    category_name = category.name
    result = delete_branch_category(category)
    if result == "deleted":
        messages.success(request, f"Categoria {category_name} eliminada.")
    elif result == "deactivated":
        messages.warning(
            request,
            f"Categoria {category_name} inactivada porque ya tiene asistentes asociados.",
        )
    else:
        messages.info(request, f"La categoria {category_name} ya estaba inactiva.")
    return redirect(_catalog_categories_redirect())
