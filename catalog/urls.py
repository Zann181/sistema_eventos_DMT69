from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("new/", views.product_create, name="create"),
    path("products/<int:product_id>/update/", views.product_update, name="product_update"),
    path("products/<int:product_id>/delete/", views.product_delete, name="product_delete"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<int:category_id>/update/", views.category_update, name="category_update"),
    path("categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),
]
