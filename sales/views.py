from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from catalog.models import Product
from identity.application import user_can_access_sales, user_can_manage_events
from sales.application import (
    build_event_product_rows,
    build_grouped_sales,
    build_bar_sales_stats,
    calculate_sale_cart_total,
    create_cash_movement,
    delete_cash_movement,
    delete_sale,
    parse_sale_cart,
    parse_event_product_rows,
    process_sale_cart,
    process_sale,
    resolve_expense_payments,
    resolve_sale_payments,
    retire_product,
    summarize_payment_methods,
    sync_event_products,
    update_cash_movement,
)
from sales.forms import BarProductForm, CashDropForm, ExpenseForm, SaleForm
from sales.models import BarSale, CashMovement, EventProduct


def _sales_permissions_guard(request):
    branch = getattr(request, "current_branch", None)
    event = getattr(request, "current_event", None)
    if not branch or not event:
        messages.error(request, "Selecciona sucursal y evento.")
        return None, None
    if not user_can_access_sales(request.user, branch, event):
        messages.error(request, "No tienes permisos para acceder al modulo de barra.")
        return None, None
    return branch, event


def _can_manage_bar_configuration(user, branch, event):
    return user_can_manage_events(user, branch, event)


def _get_editing_cash_movement(branch, event, module, movement_type, movement_id):
    if not movement_id:
        return None
    return (
        CashMovement.objects.filter(
            pk=movement_id,
            branch=branch,
            event=event,
            module=module,
            movement_type=movement_type,
        )
        .select_related("created_by")
        .prefetch_related("payments")
        .first()
    )


def _build_expense_form(movement=None):
    initial = {}
    if movement is not None:
        initial = {
            "amount": movement.total_amount,
            "description": movement.description,
        }
    return ExpenseForm(initial=initial)


def _build_cash_drop_form(movement=None):
    initial = {}
    if movement is not None:
        initial = {
            "amount": movement.total_amount,
            "description": movement.description,
        }
    return CashDropForm(initial=initial)


def _expense_payment_inputs_present(request, *, prefix):
    if (request.POST.get("payment_method") or "").strip():
        return True
    for index in range(1, 5):
        if (
            (request.POST.get(f"{prefix}_payment_method_{index}") or "").strip()
            or (request.POST.get(f"{prefix}_payment_amount_{index}") or "").strip()
            or (request.POST.get(f"{prefix}_payment_reference_{index}") or "").strip()
            or request.FILES.get(f"{prefix}_payment_proof_{index}")
        ):
            return True
    return False


def _build_cash_snapshot(branch, event):
    movement_queryset = CashMovement.objects.filter(
        branch=branch,
        event=event,
        module=CashMovement.MODULE_BAR,
    )

    sales_stats = build_bar_sales_stats(branch=branch, event=event)
    expense_total = (
        movement_queryset.filter(movement_type=CashMovement.TYPE_EXPENSE).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0.00")
    )
    cash_drop_total = (
        movement_queryset.filter(movement_type=CashMovement.TYPE_CASH_DROP).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0.00")
    )
    sales_total = sales_stats["total_amount"] or Decimal("0.00")

    enabled_products = EventProduct.objects.filter(
        branch=branch,
        event=event,
        is_enabled=True,
        event_price__isnull=False,
    ).count()
    total_products = Product.objects.filter(branch=branch, is_active=True).count()

    return {
        "sales_total": sales_total,
        "units_sold": sales_stats["total_units"] or 0,
        "sales_count": sales_stats["total_sales"] or 0,
        "expense_total": expense_total,
        "cash_drop_total": cash_drop_total,
        "cash_balance": sales_total - expense_total - cash_drop_total,
        "enabled_products": enabled_products,
        "disabled_products": max(total_products - enabled_products, 0),
        "total_products": total_products,
    }


def _pos_context(
    branch,
    event,
    *,
    sale_form=None,
    expense_form=None,
    cash_drop_form=None,
    product_form=None,
    initial_action="",
    editing_expense=None,
    editing_cash_drop=None,
    editing_product=None,
):
    sale_form = sale_form or SaleForm(branch=branch, event=event)
    recent_sales = (
        BarSale.objects.filter(branch=branch, event=event)
        .select_related("product", "attendee", "sold_by")
        .prefetch_related("payments")
        [:20]
    )
    cash_movements = (
        CashMovement.objects.filter(branch=branch, event=event, module=CashMovement.MODULE_BAR)
        .select_related("created_by")
        .prefetch_related("payments")
        [:10]
    )
    expense_movements = (
        CashMovement.objects.filter(
            branch=branch,
            event=event,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_EXPENSE,
        )
        .select_related("created_by")
        .prefetch_related("payments")
        [:10]
    )
    cash_drop_movements = (
        CashMovement.objects.filter(
            branch=branch,
            event=event,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_CASH_DROP,
        )
        .select_related("created_by")
        .prefetch_related("payments")
        [:10]
    )
    event_product_rows = build_event_product_rows(branch=branch, event=event)
    return {
        "form": sale_form,
        "expense_form": expense_form or _build_expense_form(editing_expense),
        "cash_drop_form": cash_drop_form or _build_cash_drop_form(editing_cash_drop),
        "product_form": product_form or BarProductForm(instance=editing_product),
        "sales": recent_sales,
        "cash_movements": cash_movements,
        "expense_movements": expense_movements,
        "cash_drop_movements": cash_drop_movements,
        "branch": branch,
        "event": event,
        "stats": _build_cash_snapshot(branch, event),
        "payment_method_totals": summarize_payment_methods(branch=branch, event=event),
        "event_product_rows": event_product_rows,
        "sale_products": sale_form.fields["event_product"].queryset,
        "initial_action": initial_action,
        "editing_expense": editing_expense,
        "editing_cash_drop": editing_cash_drop,
        "editing_product": editing_product,
    }


@login_required
def point_of_sale(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")

    editing_expense = None
    editing_cash_drop = None
    editing_product = None
    if _can_manage_bar_configuration(request.user, branch, event):
        editing_expense = _get_editing_cash_movement(
            branch,
            event,
            CashMovement.MODULE_BAR,
            CashMovement.TYPE_EXPENSE,
            request.GET.get("edit_expense"),
        )
        editing_cash_drop = _get_editing_cash_movement(
            branch,
            event,
            CashMovement.MODULE_BAR,
            CashMovement.TYPE_CASH_DROP,
            request.GET.get("edit_cash_drop"),
        )
        editing_product = (
            Product.objects.filter(branch=branch, pk=request.GET.get("edit_product")).first()
            if request.GET.get("edit_product")
            else None
        )

    return render(
        request,
        "sales/pos.html",
        _pos_context(
            branch,
            event,
            initial_action=request.GET.get("action", ""),
            editing_expense=editing_expense,
            editing_cash_drop=editing_cash_drop,
            editing_product=editing_product,
        ),
    )


@login_required
def sales_list(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")

    sales_queryset = (
        build_grouped_sales(branch=branch, event=event)
    )
    paginator = Paginator(sales_queryset, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "sales/list.html",
        {
            "branch": branch,
            "event": event,
            "sales_page": page,
            "stats": _build_cash_snapshot(branch, event),
        },
    )


@require_POST
@login_required
def sale_create(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return JsonResponse({"success": False, "message": "Sin permisos para barra."}, status=403)

    raw_cart = (request.POST.get("sale_cart") or "").strip()
    if raw_cart:
        try:
            cart_items = parse_sale_cart(raw_cart)
            total_amount = calculate_sale_cart_total(branch=branch, event=event, items=cart_items)
            payments = resolve_sale_payments(request.POST, request.FILES, total_amount=total_amount, prefix="sale")
            sales = process_sale_cart(
                branch=branch,
                event=event,
                user=request.user,
                items=cart_items,
                payments=payments,
            )
        except ValueError as exc:
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

        sold_products = ", ".join(f"{sale.product.name} x{sale.quantity}" for sale in sales)
        return JsonResponse(
            {
                "success": True,
                "message": "Venta registrada.",
                "sale": {
                    "items": len(sales),
                    "products": sold_products,
                    "total": float(sum(sale.total for sale in sales)),
                },
            }
        )

    form = SaleForm(request.POST, branch=branch, event=event)
    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0] if form.errors else "Formulario invalido."
        return JsonResponse({"success": False, "message": first_error}, status=400)

    event_product = form.cleaned_data["event_product"]
    quantity = form.cleaned_data["quantity"]
    total_amount = Decimal(event_product.effective_price) * Decimal(quantity)

    try:
        payments = []
        if not form.cleaned_data["use_included_balance"]:
            payments = resolve_sale_payments(request.POST, request.FILES, total_amount=total_amount, prefix="sale")
        sale = process_sale(
            branch=branch,
            event=event,
            event_product=event_product,
            quantity=quantity,
            user=request.user,
            attendee=form.cleaned_data["attendee"],
            use_included_balance=form.cleaned_data["use_included_balance"],
            payments=payments,
        )
    except ValueError as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)

    payment_summary = ", ".join(payment.get_method_display() for payment in sale.payments.all()) or "Consumo incluido"
    return JsonResponse(
        {
            "success": True,
            "message": "Venta registrada.",
            "sale": {
                "product": sale.product.name,
                "quantity": sale.quantity,
                "total": float(sale.total),
                "unit_price": float(sale.unit_price),
                "payments": payment_summary,
            },
        }
    )


@require_POST
@login_required
def product_create(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not user_can_manage_events(request.user, branch, event):
        messages.error(request, "No tienes permisos para agregar productos en este evento.")
        return redirect("shared_ui:dashboard")

    form = BarProductForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del producto.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(branch, event, product_form=form, initial_action="productos"),
            status=400,
        )

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


@require_POST
@login_required
def product_update(request, product_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden modificar productos.")
        return redirect("shared_ui:dashboard")

    product = Product.objects.filter(branch=branch, pk=product_id).first()
    if product is None:
        raise Http404("El producto no existe.")

    form = BarProductForm(request.POST, request.FILES, instance=product)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del producto.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(branch, event, product_form=form, initial_action="evento-productos", editing_product=product),
            status=400,
        )

    updated_product = form.save()
    messages.success(request, f"Producto global {updated_product.name} actualizado.")
    return redirect(f"{reverse('sales:pos')}?action=evento-productos")


@require_POST
@login_required
def product_delete(request, product_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden eliminar productos.")
        return redirect("shared_ui:dashboard")

    product = Product.objects.filter(branch=branch, pk=product_id).first()
    if product is None:
        raise Http404("El producto no existe.")

    result = retire_product(branch=branch, product=product, user=request.user)
    if result["mode"] == "retired":
        messages.success(
            request,
            f"Producto {product.name} retirado globalmente. Se desactivo para conservar el historial.",
        )
    else:
        messages.success(request, f"Producto global {product.name} eliminado.")
    return redirect(f"{reverse('sales:pos')}?action=evento-productos")


@require_POST
@login_required
def sale_delete(request, sale_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")

    try:
        sale = delete_sale(branch=branch, event=event, sale_id=sale_id)
    except BarSale.DoesNotExist as exc:
        raise Http404("La venta ya no existe.") from exc

    messages.success(
        request,
        f"Venta eliminada: {sale['products']} por $ {sale['total']}.",
    )
    return redirect("sales:list")


@require_POST
@login_required
def event_products_update(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not user_can_manage_events(request.user, branch, event):
        messages.error(request, "No tienes permisos para configurar productos del evento.")
        return redirect("shared_ui:dashboard")

    try:
        rows = parse_event_product_rows(request.POST)
        updated = sync_event_products(branch=branch, event=event, user=request.user, rows=rows)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('sales:pos')}?action=evento-productos")

    messages.success(request, f"Configuracion de productos actualizada ({updated} productos).")
    return redirect("sales:pos")


@require_POST
@login_required
def expense_create(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")

    form = ExpenseForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del gasto.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(branch, event, expense_form=form, initial_action="gastos"),
            status=400,
        )

    try:
        payments = resolve_expense_payments(request.POST, request.FILES, form, prefix="expense")
        create_cash_movement(
            branch=branch,
            event=event,
            user=request.user,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_EXPENSE,
            total_amount=form.cleaned_data["amount"],
            description=form.cleaned_data["description"],
            payments=payments,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('sales:pos')}?action=gastos")

    messages.success(request, "Gasto registrado en barra.")
    return redirect("sales:pos")


@require_POST
@login_required
def expense_update(request, movement_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden modificar gastos.")
        return redirect("shared_ui:dashboard")

    movement = get_object_or_404(
        CashMovement,
        pk=movement_id,
        branch=branch,
        event=event,
        module=CashMovement.MODULE_BAR,
        movement_type=CashMovement.TYPE_EXPENSE,
    )
    form = ExpenseForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del gasto.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(
                branch,
                event,
                expense_form=form,
                initial_action="gastos",
                editing_expense=movement,
            ),
            status=400,
        )

    payments = None
    if _expense_payment_inputs_present(request, prefix="expense"):
        try:
            payments = resolve_expense_payments(request.POST, request.FILES, form, prefix="expense")
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "sales/pos.html",
                _pos_context(
                    branch,
                    event,
                    expense_form=form,
                    initial_action="gastos",
                    editing_expense=movement,
                ),
                status=400,
            )

    try:
        update_cash_movement(
            movement=movement,
            total_amount=form.cleaned_data["amount"],
            description=form.cleaned_data["description"],
            payments=payments,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('sales:pos')}?action=gastos&edit_expense={movement.id}")

    messages.success(request, "Gasto actualizado en barra.")
    return redirect(f"{reverse('sales:pos')}?action=gastos")


@require_POST
@login_required
def expense_delete(request, movement_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden eliminar gastos.")
        return redirect("shared_ui:dashboard")

    movement = get_object_or_404(
        CashMovement,
        pk=movement_id,
        branch=branch,
        event=event,
        module=CashMovement.MODULE_BAR,
        movement_type=CashMovement.TYPE_EXPENSE,
    )
    delete_cash_movement(movement=movement)
    messages.success(request, "Gasto eliminado de barra.")
    return redirect(f"{reverse('sales:pos')}?action=gastos")


@require_POST
@login_required
def cash_drop_create(request):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")

    form = CashDropForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del vaciado de caja.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(branch, event, cash_drop_form=form, initial_action="vaciar-caja"),
            status=400,
        )

    try:
        create_cash_movement(
            branch=branch,
            event=event,
            user=request.user,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_CASH_DROP,
            total_amount=form.cleaned_data["amount"],
            description=form.cleaned_data["description"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('sales:pos')}?action=vaciar-caja")

    messages.success(request, "Vaciado de caja registrado en barra.")
    return redirect("sales:pos")


@require_POST
@login_required
def cash_drop_update(request, movement_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden modificar vaciados de caja.")
        return redirect("shared_ui:dashboard")

    movement = get_object_or_404(
        CashMovement,
        pk=movement_id,
        branch=branch,
        event=event,
        module=CashMovement.MODULE_BAR,
        movement_type=CashMovement.TYPE_CASH_DROP,
    )
    form = CashDropForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Corrige los datos del vaciado de caja.")
        return render(
            request,
            "sales/pos.html",
            _pos_context(
                branch,
                event,
                cash_drop_form=form,
                initial_action="vaciar-caja",
                editing_cash_drop=movement,
            ),
            status=400,
        )

    try:
        update_cash_movement(
            movement=movement,
            total_amount=form.cleaned_data["amount"],
            description=form.cleaned_data["description"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('sales:pos')}?action=vaciar-caja&edit_cash_drop={movement.id}")

    messages.success(request, "Vaciado de caja actualizado en barra.")
    return redirect(f"{reverse('sales:pos')}?action=vaciar-caja")


@require_POST
@login_required
def cash_drop_delete(request, movement_id):
    branch, event = _sales_permissions_guard(request)
    if not branch or not event:
        return redirect("shared_ui:dashboard")
    if not _can_manage_bar_configuration(request.user, branch, event):
        messages.error(request, "Solo los administradores pueden eliminar vaciados de caja.")
        return redirect("shared_ui:dashboard")

    movement = get_object_or_404(
        CashMovement,
        pk=movement_id,
        branch=branch,
        event=event,
        module=CashMovement.MODULE_BAR,
        movement_type=CashMovement.TYPE_CASH_DROP,
    )
    delete_cash_movement(movement=movement)
    messages.success(request, "Vaciado de caja eliminado de barra.")
    return redirect(f"{reverse('sales:pos')}?action=vaciar-caja")
