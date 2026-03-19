from django.urls import path

from sales import views

app_name = "sales"

urlpatterns = [
    path("", views.point_of_sale, name="pos"),
    path("ventas/", views.sales_list, name="list"),
    path("create/", views.sale_create, name="create"),
    path("ventas/<int:sale_id>/delete/", views.sale_delete, name="delete"),
    path("products/new/", views.product_create, name="product_create"),
    path("products/<int:product_id>/update/", views.product_update, name="product_update"),
    path("products/<int:product_id>/delete/", views.product_delete, name="product_delete"),
    path("products/event-config/", views.event_products_update, name="event_products_update"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<int:movement_id>/update/", views.expense_update, name="expense_update"),
    path("expenses/<int:movement_id>/delete/", views.expense_delete, name="expense_delete"),
    path("cash-drop/new/", views.cash_drop_create, name="cash_drop_create"),
    path("cash-drop/<int:movement_id>/update/", views.cash_drop_update, name="cash_drop_update"),
    path("cash-drop/<int:movement_id>/delete/", views.cash_drop_delete, name="cash_drop_delete"),
]
