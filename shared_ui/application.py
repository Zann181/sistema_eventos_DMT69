import json
import math
from decimal import Decimal

from django.db.models import Count, Q, Sum

from attendees.models import Attendee, Category
from catalog.models import Product
from sales.application import build_bar_product_rows, build_bar_sales_stats
from sales.models import BarSalePayment, CashMovement, CashMovementPayment


PIE_COLORS = ["#39ff14", "#59f4ad", "#8aff64", "#00e676", "#b6ff7a", "#45ffb0", "#d2ff92"]


def _sum_or_zero(queryset, field):
    return queryset.aggregate(total=Sum(field)).get("total") or Decimal("0")


def _polar_to_cartesian(radius, angle_degrees):
    angle_radians = math.radians(angle_degrees - 90)
    return (
        50 + (radius * math.cos(angle_radians)),
        50 + (radius * math.sin(angle_radians)),
    )


def _build_pie_slice_path(start_angle, end_angle, radius=46):
    sweep = end_angle - start_angle
    if sweep <= 0:
        return ""
    if sweep >= 360:
        return (
            f"M 50 50 "
            f"m 0 {-radius} "
            f"a {radius} {radius} 0 1 1 0 {radius * 2} "
            f"a {radius} {radius} 0 1 1 0 {-radius * 2}"
        )

    start_x, start_y = _polar_to_cartesian(radius, start_angle)
    end_x, end_y = _polar_to_cartesian(radius, end_angle)
    large_arc = 1 if sweep > 180 else 0
    return (
        f"M 50 50 "
        f"L {start_x:.4f} {start_y:.4f} "
        f"A {radius} {radius} 0 {large_arc} 1 {end_x:.4f} {end_y:.4f} Z"
    )


def build_pie_chart(segments):
    prepared = []
    total = sum(Decimal(segment["value"]) for segment in segments)
    cursor = Decimal("0")
    gradient_parts = []

    for index, segment in enumerate(segments):
        value = Decimal(segment["value"])
        share = (value / total * Decimal("100")) if total else Decimal("0")
        start = cursor
        end = cursor + share
        mid = (start + end) / Decimal("2") if share > 0 else start
        mid_angle = float(mid * Decimal("3.6"))
        color = PIE_COLORS[index % len(PIE_COLORS)]
        if share > 0:
            gradient_parts.append(f"{color} {start:.2f}% {end:.2f}%")
        prepared.append(
            {
                **segment,
                "color": color,
                "share": float(round(share, 2)),
                "start_angle": float(round(start * Decimal("3.6"), 2)),
                "end_angle": float(round(end * Decimal("3.6"), 2)),
                "mid_angle": float(round(mid_angle, 2)),
                "offset_x": round(math.cos(math.radians(mid_angle - 90)) * 8, 2) if share > 0 else 0,
                "offset_y": round(math.sin(math.radians(mid_angle - 90)) * 8, 2) if share > 0 else 0,
                "path": _build_pie_slice_path(float(start * Decimal("3.6")), float(end * Decimal("3.6"))) if share > 0 else "",
                "detail_points_json": json.dumps(segment.get("detail_points", [])),
            }
        )
        cursor = end

    if cursor < Decimal("100"):
        gradient_parts.append(f"rgba(255, 255, 255, 0.08) {cursor:.2f}% 100%")

    return {
        "segments": prepared,
        "gradient": (
            f"conic-gradient({', '.join(gradient_parts)})"
            if gradient_parts
            else "conic-gradient(rgba(255, 255, 255, 0.08) 0 100%)"
        ),
        "total": total,
    }


def build_empty_dashboard_analytics():
    empty_chart = build_pie_chart([])
    dashboard_metrics = {
        "income_total": Decimal("0"),
        "expense_total": Decimal("0"),
        "cash_drop_total": Decimal("0"),
        "net_operating": Decimal("0"),
        "cash_balance": Decimal("0"),
    }
    entrance_metrics = {
        "attendees": 0,
        "checked_in": 0,
        "pending": 0,
        "manual_income": Decimal("0"),
        "event_day_income": Decimal("0"),
        "income_total": Decimal("0"),
        "expense_total": Decimal("0"),
        "cash_drop_total": Decimal("0"),
        "net_operating": Decimal("0"),
        "cash_balance": Decimal("0"),
    }
    bar_metrics = {
        "income_total": Decimal("0"),
        "units_sold": 0,
        "expense_total": Decimal("0"),
        "cash_drop_total": Decimal("0"),
        "net_operating": Decimal("0"),
        "cash_balance": Decimal("0"),
        "total_products": 0,
        "enabled_products": 0,
        "top_units_product_name": "Sin ventas",
        "top_units_product_units": 0,
        "top_revenue_product_name": "Sin ventas",
        "top_revenue_product_total": Decimal("0"),
    }
    combined = {
        "metrics": dashboard_metrics.copy(),
        "income_chart": empty_chart,
        "outflow_chart": empty_chart,
        "recent_cash_movements": [],
        "movement_breakdown": [],
    }
    return {
        "dashboard_summary": combined,
        "entrada_analytics": {
            "metrics": entrance_metrics,
            "categories": [],
            "payment_methods": [],
            "access_chart": empty_chart,
            "income_chart": empty_chart,
            "payments_chart": empty_chart,
            "categories_chart": empty_chart,
        },
        "barra_analytics": {
            "metrics": bar_metrics,
            "product_rows": [],
            "payment_methods": [],
            "finance_chart": empty_chart,
            "payments_chart": empty_chart,
            "products_chart": empty_chart,
        },
        "combined_analytics": combined,
    }


def _build_entry_category_summary(branch, event):
    categories = list(
        Category.objects.filter(branch=branch, is_active=True)
        .annotate(
            total=Count("attendees", filter=Q(attendees__branch=branch, attendees__event=event)),
            checked_in=Count(
                "attendees",
                filter=Q(attendees__branch=branch, attendees__event=event, attendees__has_checked_in=True),
            ),
            subtotal=Sum(
                "attendees__paid_amount",
                filter=Q(attendees__branch=branch, attendees__event=event, attendees__origin=Attendee.ORIGIN_MANUAL),
            ),
        )
        .order_by("name")
    )
    for category in categories:
        category.pending = (category.total or 0) - (category.checked_in or 0)
        category.subtotal = category.subtotal or Decimal("0")
        category.progress = int(((category.checked_in or 0) / category.total) * 100) if category.total else 0
    return categories


def _build_payment_method_segments(rows, labels, detail_body):
    total_amount = sum((row["total"] or Decimal("0")) for row in rows) or Decimal("0")
    segments = []
    methods = []
    for row in rows:
        total = row["total"] or Decimal("0")
        share = int((total / total_amount) * 100) if total_amount else 0
        label = labels.get(row["method"], row["method"].title())
        methods.append(
            {
                "label": label,
                "total": total,
                "count": row.get("count", 0) or row.get("movements", 0),
                "share": share,
            }
        )
        segments.append(
            {
                "name": label,
                "value": total,
                "detail_body": detail_body,
                "detail_points": [
                    f"Total: $ {total}",
                    f"Participacion: {share}%",
                    f"Movimientos: {row.get('count', 0) or row.get('movements', 0)}",
                ],
            }
        )
    return methods, build_pie_chart(segments)


def build_entrance_analytics(branch, event):
    attendees = Attendee.objects.filter(branch=branch, event=event)
    entry_movements = CashMovement.objects.filter(branch=branch, event=event, module=CashMovement.MODULE_ENTRANCE)
    total_attendees = attendees.count()
    checked_in = attendees.filter(has_checked_in=True).count()
    pending = attendees.filter(has_checked_in=False).count()
    manual_income = _sum_or_zero(attendees.filter(origin=Attendee.ORIGIN_MANUAL), "paid_amount")
    event_day_income = _sum_or_zero(entry_movements.filter(movement_type=CashMovement.TYPE_EVENT_DAY), "total_amount")
    income_total = manual_income + event_day_income
    expense_total = _sum_or_zero(entry_movements.filter(movement_type=CashMovement.TYPE_EXPENSE), "total_amount")
    cash_drop_total = _sum_or_zero(entry_movements.filter(movement_type=CashMovement.TYPE_CASH_DROP), "total_amount")
    net_operating = income_total - expense_total
    cash_balance = income_total - expense_total - cash_drop_total

    categories = _build_entry_category_summary(branch, event)
    category_segments = [
        {
            "name": category.name,
            "value": category.total or 0,
            "detail_body": "Detalle operativo de la categoria en el evento activo.",
            "detail_points": [
                f"Ingresaron: {category.checked_in or 0}",
                f"Pendientes: {category.pending or 0}",
                f"Total: {category.total or 0}",
                f"Subtotal manual: $ {category.subtotal or 0}",
            ],
        }
        for category in categories
    ]

    payment_rows = list(
        CashMovementPayment.objects.filter(
            movement__branch=branch,
            movement__event=event,
            movement__module=CashMovement.MODULE_ENTRANCE,
            movement__movement_type=CashMovement.TYPE_EVENT_DAY,
        )
        .values("method")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    payment_labels = dict(CashMovementPayment.METHOD_CHOICES)
    payment_methods, payments_chart = _build_payment_method_segments(
        payment_rows,
        payment_labels,
        "Pagos registrados para movimientos de Dia del evento.",
    )

    return {
        "metrics": {
            "attendees": total_attendees,
            "checked_in": checked_in,
            "pending": pending,
            "manual_income": manual_income,
            "event_day_income": event_day_income,
            "income_total": income_total,
            "expense_total": expense_total,
            "cash_drop_total": cash_drop_total,
            "net_operating": net_operating,
            "cash_balance": cash_balance,
        },
        "categories": categories,
        "payment_methods": payment_methods,
        "access_chart": build_pie_chart(
            [
                {
                    "name": "Ingresaron",
                    "value": checked_in,
                    "detail_body": "Asistentes con check-in confirmado en el evento activo.",
                    "detail_points": [
                        f"Total: {checked_in}",
                        f"Pendientes: {pending}",
                        f"Base del evento: {total_attendees} asistentes",
                    ],
                },
                {
                    "name": "Pendientes",
                    "value": pending,
                    "detail_body": "Asistentes registrados que aun no han ingresado.",
                    "detail_points": [
                        f"Total: {pending}",
                        f"Ingresaron: {checked_in}",
                        f"Base del evento: {total_attendees} asistentes",
                    ],
                },
            ]
        ),
        "income_chart": build_pie_chart(
            [
                {
                    "name": "Entrada manual",
                    "value": manual_income,
                    "detail_body": "Ingresos provenientes de asistentes registrados manualmente.",
                    "detail_points": [
                        f"Manual: $ {manual_income}",
                        f"Dia del evento: $ {event_day_income}",
                        f"Total entrada: $ {income_total}",
                    ],
                },
                {
                    "name": "Dia del evento",
                    "value": event_day_income,
                    "detail_body": "Ingresos de caja generados desde el modulo Dia del evento.",
                    "detail_points": [
                        f"Dia del evento: $ {event_day_income}",
                        f"Manual: $ {manual_income}",
                        f"Total entrada: $ {income_total}",
                    ],
                },
            ]
        ),
        "payments_chart": payments_chart,
        "categories_chart": build_pie_chart(category_segments),
    }


def build_bar_analytics(branch, event):
    bar_movements = CashMovement.objects.filter(branch=branch, event=event, module=CashMovement.MODULE_BAR)
    sales_stats = build_bar_sales_stats(branch=branch, event=event)
    income_total = sales_stats["total_amount"] or Decimal("0")
    units_sold = sales_stats["total_units"] or 0
    expense_total = _sum_or_zero(bar_movements.filter(movement_type=CashMovement.TYPE_EXPENSE), "total_amount")
    cash_drop_total = _sum_or_zero(bar_movements.filter(movement_type=CashMovement.TYPE_CASH_DROP), "total_amount")
    net_operating = income_total - expense_total
    cash_balance = income_total - expense_total - cash_drop_total
    total_products = Product.objects.filter(is_active=True).count()
    enabled_products = Product.objects.filter(
        is_active=True,
        event_settings__branch=branch,
        event_settings__event=event,
        event_settings__is_enabled=True,
        event_settings__event_price__isnull=False,
    ).distinct().count()

    product_rows = build_bar_product_rows(branch=branch, event=event)
    top_units_product = product_rows[0] if product_rows else None
    top_revenue_product = max(product_rows, key=lambda item: item["revenue"] or Decimal("0"), default=None)
    product_segments_rows = product_rows[:6]
    if len(product_rows) > 6:
        other_units = sum((row["units"] or 0) for row in product_rows[6:])
        other_revenue = sum((row["revenue"] or Decimal("0")) for row in product_rows[6:])
        if other_units:
            product_segments_rows.append(
                {
                    "product__name": "Otros productos",
                    "units": other_units,
                    "revenue": other_revenue,
                    "sales_count": sum((row["sales_count"] or 0) for row in product_rows[6:]),
                }
            )

    payment_rows = list(
        BarSalePayment.objects.filter(sale__branch=branch, sale__event=event)
        .values("method")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    payment_labels = dict(CashMovementPayment.METHOD_CHOICES)
    payment_methods, payments_chart = _build_payment_method_segments(
        payment_rows,
        payment_labels,
        "Pagos registrados en ventas de barra.",
    )

    return {
        "metrics": {
            "income_total": income_total,
            "units_sold": units_sold,
            "expense_total": expense_total,
            "cash_drop_total": cash_drop_total,
            "net_operating": net_operating,
            "cash_balance": cash_balance,
            "total_products": total_products,
            "enabled_products": enabled_products,
            "top_units_product_name": top_units_product["product__name"] if top_units_product else "Sin ventas",
            "top_units_product_units": top_units_product["units"] if top_units_product else 0,
            "top_revenue_product_name": top_revenue_product["product__name"] if top_revenue_product else "Sin ventas",
            "top_revenue_product_total": top_revenue_product["revenue"] if top_revenue_product else Decimal("0"),
        },
        "product_rows": product_rows,
        "payment_methods": payment_methods,
        "finance_chart": build_pie_chart(
            [
                {
                    "name": "Ingresos barra",
                    "value": income_total,
                    "detail_body": "Total vendido desde punto de venta.",
                    "detail_points": [
                        f"Vendido: $ {income_total}",
                        f"Gastos: $ {expense_total}",
                        f"Vaciado: $ {cash_drop_total}",
                    ],
                },
                {
                    "name": "Gastos barra",
                    "value": expense_total,
                    "detail_body": "Gastos registrados en el modulo Barra.",
                    "detail_points": [
                        f"Gastos: $ {expense_total}",
                        f"Vendido: $ {income_total}",
                        f"Vaciado: $ {cash_drop_total}",
                    ],
                },
                {
                    "name": "Vaciado barra",
                    "value": cash_drop_total,
                    "detail_body": "Retiros de caja registrados en Barra.",
                    "detail_points": [
                        f"Vaciado: $ {cash_drop_total}",
                        f"Vendido: $ {income_total}",
                        f"Gastos: $ {expense_total}",
                    ],
                },
            ]
        ),
        "payments_chart": payments_chart,
        "products_chart": build_pie_chart(
            [
                {
                    "name": row["product__name"],
                    "value": row["units"] or 0,
                    "detail_body": "Participacion por unidades vendidas en Barra.",
                    "detail_points": [
                        f"Unidades: {row['units'] or 0}",
                        f"Facturacion: $ {row['revenue'] or 0}",
                        f"Ventas: {row['sales_count'] or 0}",
                    ],
                }
                for row in product_segments_rows
            ]
        ),
    }


def build_combined_analytics(branch, event, entrance_analytics, bar_analytics):
    entrance_metrics = entrance_analytics["metrics"]
    bar_metrics = bar_analytics["metrics"]
    income_total = entrance_metrics["income_total"] + bar_metrics["income_total"]
    expense_total = entrance_metrics["expense_total"] + bar_metrics["expense_total"]
    cash_drop_total = entrance_metrics["cash_drop_total"] + bar_metrics["cash_drop_total"]
    net_operating = income_total - expense_total
    cash_balance = income_total - expense_total - cash_drop_total

    recent_cash_movements = list(
        CashMovement.objects.filter(
            branch=branch,
            event=event,
            movement_type__in=[CashMovement.TYPE_EVENT_DAY, CashMovement.TYPE_EXPENSE, CashMovement.TYPE_CASH_DROP],
        )
        .select_related("created_by")
        .order_by("-created_at")[:12]
    )
    movement_breakdown_rows = (
        CashMovement.objects.filter(
            branch=branch,
            event=event,
            movement_type__in=[CashMovement.TYPE_EXPENSE, CashMovement.TYPE_CASH_DROP],
        )
        .values("module", "movement_type", "created_role", "created_by__username")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("module", "movement_type", "created_by__username", "created_role")
    )
    role_labels = dict(CashMovement.CREATED_ROLE_CHOICES)
    type_labels = dict(CashMovement.TYPE_CHOICES)
    module_labels = dict(CashMovement.MODULE_CHOICES)
    movement_breakdown = [
        {
            "module": row["module"],
            "module_label": module_labels.get(row["module"], row["module"]),
            "movement_type": row["movement_type"],
            "movement_type_label": type_labels.get(row["movement_type"], row["movement_type"]),
            "created_role": row["created_role"] or "",
            "created_role_label": role_labels.get(row["created_role"], "Sin rol"),
            "created_by_username": row["created_by__username"] or "Usuario eliminado",
            "count": row["count"] or 0,
            "total": row["total"] or Decimal("0"),
        }
        for row in movement_breakdown_rows
    ]

    return {
        "metrics": {
            "income_total": income_total,
            "expense_total": expense_total,
            "cash_drop_total": cash_drop_total,
            "net_operating": net_operating,
            "cash_balance": cash_balance,
        },
        "recent_cash_movements": recent_cash_movements,
        "movement_breakdown": movement_breakdown,
        "income_chart": build_pie_chart(
            [
                {
                    "name": "Entrada",
                    "value": entrance_metrics["income_total"],
                    "detail_body": "Ingresos totales del modulo Entrada en el evento activo.",
                    "detail_points": [
                        f"Entrada manual: $ {entrance_metrics['manual_income']}",
                        f"Dia del evento: $ {entrance_metrics['event_day_income']}",
                        f"Total entrada: $ {entrance_metrics['income_total']}",
                    ],
                },
                {
                    "name": "Barra",
                    "value": bar_metrics["income_total"],
                    "detail_body": "Ingresos totales del modulo Barra en el evento activo.",
                    "detail_points": [
                        f"Total vendido: $ {bar_metrics['income_total']}",
                        f"Unidades vendidas: {bar_metrics['units_sold']}",
                        f"Saldo barra: $ {bar_metrics['cash_balance']}",
                    ],
                },
            ]
        ),
        "outflow_chart": build_pie_chart(
            [
                {
                    "name": "Gastos entrada",
                    "value": entrance_metrics["expense_total"],
                    "detail_body": "Gastos registrados en el modulo Entrada.",
                    "detail_points": [
                        f"Gastos entrada: $ {entrance_metrics['expense_total']}",
                        f"Vaciado entrada: $ {entrance_metrics['cash_drop_total']}",
                    ],
                },
                {
                    "name": "Gastos barra",
                    "value": bar_metrics["expense_total"],
                    "detail_body": "Gastos registrados en el modulo Barra.",
                    "detail_points": [
                        f"Gastos barra: $ {bar_metrics['expense_total']}",
                        f"Vaciado barra: $ {bar_metrics['cash_drop_total']}",
                    ],
                },
                {
                    "name": "Vaciado entrada",
                    "value": entrance_metrics["cash_drop_total"],
                    "detail_body": "Retiros de caja del modulo Entrada.",
                    "detail_points": [
                        f"Vaciado entrada: $ {entrance_metrics['cash_drop_total']}",
                        f"Gastos entrada: $ {entrance_metrics['expense_total']}",
                    ],
                },
                {
                    "name": "Vaciado barra",
                    "value": bar_metrics["cash_drop_total"],
                    "detail_body": "Retiros de caja del modulo Barra.",
                    "detail_points": [
                        f"Vaciado barra: $ {bar_metrics['cash_drop_total']}",
                        f"Gastos barra: $ {bar_metrics['expense_total']}",
                    ],
                },
            ]
        ),
    }


def build_dashboard_analytics(branch, event):
    entrance_analytics = build_entrance_analytics(branch, event)
    bar_analytics = build_bar_analytics(branch, event)
    combined_analytics = build_combined_analytics(branch, event, entrance_analytics, bar_analytics)
    return {
        "dashboard_summary": combined_analytics,
        "entrada_analytics": entrance_analytics,
        "barra_analytics": bar_analytics,
        "combined_analytics": combined_analytics,
    }
