from decimal import Decimal, InvalidOperation
import json
import uuid

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from attendees.models import Attendee
from catalog.models import Product
from sales.models import BarSale, BarSalePayment, CashMovement, CashMovementPayment, EventProduct


@transaction.atomic
def ensure_event_product_defaults(*, branch, event, user=None):
    products = list(Product.objects.filter(is_active=True))
    existing_configs = {
        config.product_id: config
        for config in EventProduct.objects.filter(branch=branch, event=event, product__in=products)
    }
    created = 0
    for product in products:
        if product.id in existing_configs:
            continue
        EventProduct.objects.create(
            branch=branch,
            event=event,
            product=product,
            is_enabled=False,
            event_price=None,
            updated_by=user,
        )
        created += 1
    return created


@transaction.atomic
def process_sale(
    *,
    branch,
    event,
    product: Product | None = None,
    event_product: EventProduct | None = None,
    quantity: int,
    user,
    attendee: Attendee | None = None,
    use_included_balance: bool = False,
    payments=None,
):
    if event_product is not None:
        product = event_product.product
    if product is None:
        raise ValueError("Debes seleccionar un producto.")
    if event_product and event_product.event_id != event.id:
        raise ValueError("El producto no esta configurado para el evento activo.")
    if event_product and not event_product.is_enabled:
        raise ValueError("El producto no esta habilitado para este evento.")
    if attendee and attendee.branch_id != branch.id:
        raise ValueError("El asistente no pertenece a la sucursal activa.")
    if attendee and attendee.event_id != event.id:
        raise ValueError("El asistente no pertenece al evento activo.")
    if attendee and use_included_balance and attendee.included_balance < quantity:
        raise ValueError("Consumos incluidos insuficientes.")

    unit_price = event_product.effective_price if event_product is not None else None
    if unit_price is None:
        raise ValueError("El producto no tiene precio configurado para este evento.")
    total = Decimal(unit_price) * Decimal(quantity)
    payments = payments or []
    if use_included_balance:
        payments = []
    elif not payments:
        raise ValueError("Debes registrar al menos una forma de pago.")

    sale = BarSale.objects.create(
        branch=branch,
        event=event,
        sale_group=uuid.uuid4(),
        attendee=attendee,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        total=total,
        used_included_consumption=use_included_balance,
        sold_by=user,
    )

    if payments:
        payment_total = sum(Decimal(payment["amount"]) for payment in payments)
        if payment_total != total:
            raise ValueError("La suma de las formas de pago debe coincidir con el total.")
        for payment in payments:
            BarSalePayment.objects.create(
                sale=sale,
                method=payment["method"],
                amount=payment["amount"],
                reference=payment.get("reference", ""),
                transfer_proof=payment.get("transfer_proof"),
            )

    if attendee and use_included_balance:
        attendee.included_balance -= quantity
        attendee.save(update_fields=["included_balance"])

    return sale


def parse_sale_cart(raw_cart):
    if not raw_cart:
        raise ValueError("Debes agregar al menos un producto a la factura.")
    try:
        items = json.loads(raw_cart)
    except json.JSONDecodeError as exc:
        raise ValueError("La factura enviada no es valida.") from exc
    if not isinstance(items, list) or not items:
        raise ValueError("Debes agregar al menos un producto a la factura.")

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("La factura enviada no es valida.")
        product_id = str(item.get("event_product_id") or "").strip()
        quantity = item.get("quantity")
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cada producto de la factura debe tener una cantidad valida.") from exc
        if not product_id or quantity <= 0:
            raise ValueError("Cada producto de la factura debe tener una cantidad valida.")
        normalized.append({"event_product_id": product_id, "quantity": quantity})
    return normalized


def calculate_sale_cart_total(*, branch, event, items):
    if not items:
        raise ValueError("Debes agregar al menos un producto a la factura.")

    requested_ids = [str(item["event_product_id"]) for item in items]
    event_products = {
        str(item.id): item
        for item in EventProduct.objects.select_related("product").filter(
            branch=branch,
            event=event,
            id__in=requested_ids,
            is_enabled=True,
            event_price__isnull=False,
            product__is_active=True,
        )
    }
    if len(event_products) != len(set(requested_ids)):
        raise ValueError("Uno o varios productos ya no estan disponibles para este evento.")

    total = Decimal("0.00")
    for item in items:
        total += Decimal(item["quantity"]) * Decimal(event_products[str(item["event_product_id"])].effective_price)
    return total


@transaction.atomic
def process_sale_cart(*, branch, event, user, items, payments=None):
    payments = payments or []
    if not items:
        raise ValueError("Debes agregar al menos un producto a la factura.")

    quantities_by_id = {}
    ordered_ids = []
    for item in items:
        product_id = str(item["event_product_id"])
        if product_id not in quantities_by_id:
            quantities_by_id[product_id] = 0
            ordered_ids.append(product_id)
        quantities_by_id[product_id] += int(item["quantity"])

    event_products = {
        str(item.id): item
        for item in EventProduct.objects.select_related("product").filter(
            branch=branch,
            event=event,
            id__in=ordered_ids,
            is_enabled=True,
            event_price__isnull=False,
            product__is_active=True,
        )
    }

    if len(event_products) != len(ordered_ids):
        raise ValueError("Uno o varios productos ya no estan disponibles para este evento.")

    sales = []
    line_remaining = {}
    invoice_total = Decimal("0.00")
    sale_group = uuid.uuid4()

    for product_id in ordered_ids:
        event_product = event_products[product_id]
        quantity = quantities_by_id[product_id]
        unit_price = Decimal(event_product.effective_price)
        total = unit_price * Decimal(quantity)
        sale = BarSale.objects.create(
            branch=branch,
            event=event,
            sale_group=sale_group,
            product=event_product.product,
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            used_included_consumption=False,
            sold_by=user,
        )
        sales.append(sale)
        line_remaining[sale.id] = total
        invoice_total += total

    if not payments:
        raise ValueError("Debes registrar al menos una forma de pago.")

    payment_total = sum(Decimal(payment["amount"]) for payment in payments)
    if payment_total != invoice_total:
        raise ValueError("La suma de las formas de pago debe coincidir con el total de la venta.")

    for payment in payments:
        payment_remaining = Decimal(payment["amount"])
        for sale in sales:
            if payment_remaining <= 0:
                break
            sale_remaining = line_remaining[sale.id]
            if sale_remaining <= 0:
                continue
            allocation = min(sale_remaining, payment_remaining)
            if allocation <= 0:
                continue
            BarSalePayment.objects.create(
                sale=sale,
                method=payment["method"],
                amount=allocation,
                reference=payment.get("reference", ""),
                transfer_proof=payment.get("transfer_proof"),
            )
            line_remaining[sale.id] -= allocation
            payment_remaining -= allocation
        if payment_remaining != 0:
            raise ValueError("No fue posible distribuir correctamente las formas de pago.")

    if any(remaining != 0 for remaining in line_remaining.values()):
        raise ValueError("La factura no pudo cerrarse correctamente.")

    return sales


def get_bar_sales_queryset(*, branch, event):
    return BarSale.objects.filter(branch=branch, event=event)


def build_bar_sales_stats(*, branch, event):
    sales_queryset = get_bar_sales_queryset(branch=branch, event=event)
    return sales_queryset.aggregate(
        total_amount=Sum("total"),
        total_units=Sum("quantity"),
        total_sales=Count("sale_group", distinct=True),
    )


def build_bar_product_rows(*, branch, event):
    sales_queryset = get_bar_sales_queryset(branch=branch, event=event)
    return list(
        sales_queryset.values("product__name")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum("total"),
            sales_count=Count("sale_group", distinct=True),
        )
        .order_by("-units", "-revenue", "product__name")
    )


def build_grouped_sales(*, branch, event):
    grouped_sales = []
    grouped_index = {}
    sales_queryset = (
        get_bar_sales_queryset(branch=branch, event=event)
        .select_related("product", "sold_by")
        .prefetch_related("payments")
        .order_by("-created_at")
    )
    for sale in sales_queryset:
        bucket = grouped_index.get(sale.sale_group)
        if bucket is None:
            bucket = {
                "id": sale.id,
                "sale_group": sale.sale_group,
                "created_at": sale.created_at,
                "sold_by": sale.sold_by,
                "lines": [],
                "payments": {},
                "total": Decimal("0.00"),
                "quantity": 0,
            }
            grouped_index[sale.sale_group] = bucket
            grouped_sales.append(bucket)
        bucket["lines"].append(sale)
        bucket["total"] += sale.total
        bucket["quantity"] += sale.quantity
        for payment in sale.payments.all():
            current_total = bucket["payments"].get(payment.get_method_display(), Decimal("0.00"))
            bucket["payments"][payment.get_method_display()] = current_total + payment.amount

    for bucket in grouped_sales:
        bucket["products_label"] = ", ".join(f"{line.product.name} x{line.quantity}" for line in bucket["lines"])
        bucket["payments_display"] = list(bucket["payments"].items())

    return grouped_sales


@transaction.atomic
def delete_sale(*, branch, event, sale_id):
    sale = BarSale.objects.select_related("product").get(pk=sale_id, branch=branch, event=event)
    group_sales = list(
        BarSale.objects.select_related("product").filter(
            branch=branch,
            event=event,
            sale_group=sale.sale_group,
        )
    )
    deleted_summary = {
        "products": ", ".join(f"{item.product.name} x{item.quantity}" for item in group_sales),
        "lines": len(group_sales),
        "total": sum(item.total for item in group_sales),
    }
    BarSale.objects.filter(
        branch=branch,
        event=event,
        sale_group=sale.sale_group,
    ).delete()
    return deleted_summary


def parse_decimal(value, *, field_name="valor"):
    if value in (None, ""):
        raise ValueError(f"Debes indicar {field_name}.")
    normalized = str(value).strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"El campo {field_name} no es valido.") from exc


def _format_decimal_input(value):
    if value is None:
        return ""
    normalized = Decimal(value).normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def extract_split_payments(post, files, *, prefix, max_rows=4):
    payments = []
    for index in range(1, max_rows + 1):
        method = (post.get(f"{prefix}_payment_method_{index}") or "").strip()
        raw_amount = (post.get(f"{prefix}_payment_amount_{index}") or "").strip()
        reference = (post.get(f"{prefix}_payment_reference_{index}") or "").strip()
        proof = files.get(f"{prefix}_payment_proof_{index}")
        if not method and not raw_amount and not reference and not proof:
            continue
        if not method:
            raise ValueError("Cada forma de pago debe tener un metodo seleccionado.")
        amount = parse_decimal(raw_amount, field_name="monto del pago")
        if amount <= 0:
            raise ValueError("Cada forma de pago debe ser mayor a cero.")
        payments.append(
            {
                "method": method,
                "amount": amount,
                "reference": reference,
                "transfer_proof": proof,
            }
        )
    if not payments:
        raise ValueError("Debes registrar al menos una forma de pago.")
    return payments


def resolve_expense_payments(post, files, form, *, prefix="expense", max_rows=4):
    has_split_input = False
    for index in range(1, max_rows + 1):
        if (
            (post.get(f"{prefix}_payment_method_{index}") or "").strip()
            or (post.get(f"{prefix}_payment_amount_{index}") or "").strip()
            or (post.get(f"{prefix}_payment_reference_{index}") or "").strip()
            or files.get(f"{prefix}_payment_proof_{index}")
        ):
            has_split_input = True
            break

    if has_split_input:
        return extract_split_payments(post, files, prefix=prefix, max_rows=max_rows)

    method = (form.cleaned_data.get("payment_method") or "").strip()
    if not method:
        raise ValueError("Debes registrar al menos una forma de pago.")

    return [
        {
            "method": method,
            "amount": form.cleaned_data["amount"],
            "reference": form.cleaned_data.get("reference", ""),
            "transfer_proof": form.cleaned_data.get("transfer_proof"),
        }
    ]


def resolve_sale_payments(post, files, *, total_amount, prefix="sale", max_rows=4):
    payments = extract_split_payments(post, files, prefix=prefix, max_rows=max_rows)
    payment_total = sum(Decimal(payment["amount"]) for payment in payments)
    total_amount = Decimal(total_amount)
    if payment_total < total_amount:
        raise ValueError("La suma de las formas de pago debe coincidir con el total de la venta.")
    if payment_total == total_amount:
        return payments

    change_amount = payment_total - total_amount
    remaining_change = change_amount

    for payment in reversed(payments):
        if payment["method"] != CashMovementPayment.METHOD_CASH or remaining_change <= 0:
            continue
        available_amount = Decimal(payment["amount"])
        discount = min(available_amount, remaining_change)
        payment["amount"] = available_amount - discount
        remaining_change -= discount

    if remaining_change > 0:
        raise ValueError("Las devueltas solo se pueden calcular sobre pagos en efectivo.")

    payments = [payment for payment in payments if Decimal(payment["amount"]) > 0]
    normalized_total = sum(Decimal(payment["amount"]) for payment in payments)
    if normalized_total != total_amount:
        raise ValueError("La suma de las formas de pago debe coincidir con el total de la venta.")
    return payments


def build_event_product_rows(*, branch, event):
    ensure_event_product_defaults(branch=branch, event=event)
    products = Product.objects.filter(is_active=True).order_by("name")
    configs = {
        config.product_id: config
        for config in EventProduct.objects.filter(branch=branch, event=event).select_related("product")
    }
    rows = []
    for product in products:
        config = configs.get(product.id)
        normalized_event_price = config.normalized_event_price() if config else None
        rows.append(
            {
                "product": product,
                "config": config,
                "is_enabled": config.is_enabled if config else False,
                "event_price": normalized_event_price,
                "event_price_input": _format_decimal_input(normalized_event_price),
                "effective_price": config.effective_price if config else None,
            }
        )
    return rows


def parse_event_product_rows(post):
    rows = []
    product_ids = post.getlist("event_product_ids")
    if not product_ids:
        raise ValueError("No llegaron productos para configurar.")

    products = {
        str(product.id): product
        for product in Product.objects.filter(pk__in=product_ids)
    }
    for product_id in product_ids:
        product = products.get(str(product_id))
        if product is None:
            continue
        raw_price = (post.get(f"event_product_price_{product.id}") or "").strip()
        is_enabled = post.get(f"event_product_enabled_{product.id}") == "on"
        if is_enabled and not raw_price:
            raise ValueError(f"Debes definir el precio del evento para {product.name}.")
        event_price = parse_decimal(raw_price, field_name=f"precio del producto {product.name}") if raw_price else None
        if event_price is not None and event_price <= 0:
            raise ValueError(f"El precio del evento para {product.name} debe ser mayor a cero.")
        rows.append(
            {
                "product": product,
                "is_enabled": is_enabled,
                "event_price": event_price,
            }
        )

    if not rows:
        raise ValueError("No se encontro ningun producto valido para configurar.")
    return rows


@transaction.atomic
def sync_event_products(*, branch, event, user, rows):
    updated = 0
    for row in rows:
        product = row["product"]
        if row["is_enabled"] and row["event_price"] is None:
            raise ValueError(f"Debes definir un precio para habilitar {product.name}.")
        config, _ = EventProduct.objects.get_or_create(
            branch=branch,
            event=event,
            product=product,
        )
        config.is_enabled = row["is_enabled"]
        config.event_price = row["event_price"]
        config.updated_by = user
        config.save(update_fields=["is_enabled", "event_price", "updated_by", "updated_at"])
        updated += 1
    return updated


@transaction.atomic
def retire_product(*, branch, product, user):
    has_sales = BarSale.objects.filter(product=product).exists()
    if has_sales:
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        EventProduct.objects.filter(product=product).update(
            is_enabled=False,
            event_price=None,
            updated_by=user,
        )
        return {"mode": "retired"}

    EventProduct.objects.filter(product=product).delete()
    product.delete()
    return {"mode": "deleted"}


def summarize_payment_methods(*, branch, event):
    totals = {
        key: Decimal("0.00")
        for key, _ in CashMovementPayment.METHOD_CHOICES
    }

    sale_rows = (
        BarSalePayment.objects.filter(sale__branch=branch, sale__event=event)
        .values("method")
        .annotate(total=Sum("amount"))
    )
    movement_rows = (
        CashMovementPayment.objects.filter(movement__branch=branch, movement__event=event, movement__module=CashMovement.MODULE_BAR)
        .values("method")
        .annotate(total=Sum("amount"))
    )

    for row in sale_rows:
        totals[row["method"]] += row["total"] or Decimal("0.00")
    for row in movement_rows:
        totals[row["method"]] += row["total"] or Decimal("0.00")

    labels = dict(CashMovementPayment.METHOD_CHOICES)
    return [
        {
            "method": method,
            "label": labels[method],
            "total": total,
        }
        for method, total in totals.items()
        if total > 0
    ]


@transaction.atomic
def create_cash_movement(
    *,
    branch,
    event,
    user,
    module,
    movement_type,
    total_amount,
    description="",
    payments=None,
    attendee_quantity=0,
    unit_amount=0,
):
    total_amount = Decimal(total_amount)
    if total_amount <= 0:
        raise ValueError("El valor debe ser mayor a cero.")

    payments = payments or []
    if payments:
        payment_total = sum(Decimal(payment["amount"]) for payment in payments)
        if payment_total != total_amount:
            raise ValueError("La suma de las formas de pago debe coincidir con el total.")

    from identity.application import get_effective_role

    created_role = get_effective_role(user, branch, event) or ""

    movement = CashMovement.objects.create(
        branch=branch,
        event=event,
        created_by=user,
        created_role=created_role,
        module=module,
        movement_type=movement_type,
        description=description,
        attendee_quantity=attendee_quantity,
        unit_amount=unit_amount,
        total_amount=total_amount,
    )
    for payment in payments:
        CashMovementPayment.objects.create(
            movement=movement,
            method=payment["method"],
            amount=payment["amount"],
            reference=payment.get("reference", ""),
            transfer_proof=payment.get("transfer_proof"),
        )
    return movement


@transaction.atomic
def update_cash_movement(
    *,
    movement,
    total_amount,
    description="",
    payments=None,
):
    total_amount = Decimal(total_amount)
    if total_amount <= 0:
        raise ValueError("El valor debe ser mayor a cero.")

    current_payment_total = movement.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    payments = payments if payments is not None else None

    if payments is not None:
        payment_total = sum(Decimal(payment["amount"]) for payment in payments)
        if payment_total != total_amount:
            raise ValueError("La suma de las formas de pago debe coincidir con el total.")
        movement.payments.all().delete()
        for payment in payments:
            CashMovementPayment.objects.create(
                movement=movement,
                method=payment["method"],
                amount=payment["amount"],
                reference=payment.get("reference", ""),
                transfer_proof=payment.get("transfer_proof"),
            )
    elif movement.movement_type == CashMovement.TYPE_EXPENSE and current_payment_total != total_amount:
        raise ValueError(
            "Si cambias el valor del gasto, debes volver a registrar las formas de pago.",
        )

    movement.total_amount = total_amount
    movement.description = description
    movement.save(update_fields=["total_amount", "description"])
    return movement


@transaction.atomic
def delete_cash_movement(*, movement):
    movement.delete()


def _build_event_day_identity(event, count_index):
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return (
        f"{event.name} puerta #{count_index}",
        f"PUERTA-{event.id}-{stamp}-{count_index}",
    )


@transaction.atomic
def register_event_day_entry(
    *,
    branch,
    event,
    category,
    attendee_quantity,
    unit_amount,
    user,
    description="",
    payments,
):
    if category.branch_id != branch.id:
        raise ValueError("La categoria no pertenece a la sucursal activa.")
    attendee_quantity = int(attendee_quantity)
    if attendee_quantity <= 0:
        raise ValueError("La cantidad de asistentes debe ser mayor a cero.")

    unit_amount = Decimal(unit_amount)
    if unit_amount <= 0:
        raise ValueError("El valor por asistente debe ser mayor a cero.")

    total_amount = unit_amount * Decimal(attendee_quantity)
    movement = create_cash_movement(
        branch=branch,
        event=event,
        user=user,
        module=CashMovement.MODULE_ENTRANCE,
        movement_type=CashMovement.TYPE_EVENT_DAY,
        total_amount=total_amount,
        description=description,
        payments=payments,
        attendee_quantity=attendee_quantity,
        unit_amount=unit_amount,
    )
    checked_in_at = timezone.now()
    for index in range(1, attendee_quantity + 1):
        name, cc = _build_event_day_identity(event, index)
        Attendee.objects.create(
            branch=branch,
            event=event,
            category=category,
            name=name,
            cc=cc,
            phone="",
            email="",
            origin=Attendee.ORIGIN_EVENT_DAY,
            paid_amount=unit_amount,
            has_checked_in=True,
            checked_in_at=checked_in_at,
            checked_in_by=user,
            included_balance=category.included_consumptions,
            created_by=user,
        )
    return movement
