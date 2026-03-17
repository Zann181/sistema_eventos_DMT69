from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from catalog.forms import ProductForm
from catalog.models import Product
from identity.application import require_branch_admin, user_can_access_catalog


@login_required
def product_list(request):
    branch = request.current_branch
    if not user_can_access_catalog(request.user, branch, request.current_event):
        messages.error(request, "No tienes permisos para acceder al catalogo.")
        return redirect("shared_ui:dashboard")

    products = Product.objects.order_by("name")
    form = ProductForm()
    return render(request, "catalog/list.html", {"products": products, "form": form, "branch": branch})


@login_required
def product_create(request):
    branch = require_branch_admin(request)
    if not branch:
        return redirect("shared_ui:dashboard")

    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.branch = branch
        product.created_by = request.user
        product.save()
        messages.success(request, f"Producto global {product.name} creado.")
        return redirect("catalog:list")

    return render(request, "catalog/form.html", {"form": form, "branch": branch, "title": "Nuevo producto"})
