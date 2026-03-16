import unicodedata

from django import forms

from attendees.models import Attendee
from attendees.models import Category
from catalog.models import Product
from sales.models import CashMovementPayment, EventProduct
from sales.application import ensure_event_product_defaults


class SaleForm(forms.Form):
    event_product = forms.ModelChoiceField(queryset=EventProduct.objects.none(), label="Producto")
    quantity = forms.IntegerField(min_value=1, initial=1)
    attendee = forms.ModelChoiceField(queryset=Attendee.objects.none(), required=False)
    use_included_balance = forms.BooleanField(required=False)

    def __init__(self, *args, branch=None, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch and event:
            ensure_event_product_defaults(branch=branch, event=event)
            queryset = EventProduct.objects.select_related("product").filter(
                branch=branch,
                event=event,
                is_enabled=True,
                product__is_active=True,
            ).order_by("product__name")
            self.fields["event_product"].queryset = queryset
            self.fields["event_product"].label_from_instance = lambda item: f"{item.product.name} - $ {item.effective_price}"
            self.fields["event_product"].widget.attrs["class"] = "form-select"
        if branch and event:
            self.fields["attendee"].queryset = Attendee.objects.filter(branch=branch, event=event, has_checked_in=True).order_by("name")
        self.fields["attendee"].widget.attrs["class"] = "form-select"
        self.fields["use_included_balance"].widget.attrs["class"] = "form-check-input"
        self.fields["quantity"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "numeric",
                "data-thousands": "true",
                "data-decimals": "0",
            }
        )


class BarProductForm(forms.ModelForm):
    image = forms.ImageField(required=False)

    class Meta:
        model = Product
        fields = ["name", "image", "price", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "form-control"
        self.fields["image"].widget.attrs["class"] = "form-control"
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"
        self.fields["price"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "0",
            }
        )


class EventDayEntryForm(forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.none(), label="Categoria")
    attendee_quantity = forms.IntegerField(min_value=1, initial=1, label="Cantidad de asistentes")
    unit_amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10, label="Valor por asistente")
    description = forms.CharField(required=False, label="Detalle", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        categories = Category.objects.none()
        if branch:
            categories = Category.objects.filter(branch=branch, is_active=True).order_by("name")
        self.fields["category"].queryset = categories
        self.fields["category"].label_from_instance = lambda category: category.name
        self.fields["category"].widget.attrs["class"] = "form-select"
        if branch and not self.is_bound:
            normalize = lambda value: unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").strip().lower()
            default_category = next((category for category in categories if normalize(category.name) == "dia"), None)
            if default_category:
                self.initial.setdefault("category", default_category.pk)
                self.fields["category"].initial = default_category.pk
                self.initial.setdefault("unit_amount", default_category.price)
                self.fields["unit_amount"].initial = default_category.price
        self.fields["attendee_quantity"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "numeric",
                "data-thousands": "true",
                "data-decimals": "0",
            }
        )
        self.fields["unit_amount"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "2",
            }
        )
        self.fields["description"].widget.attrs["class"] = "form-control"


class ExpenseForm(forms.Form):
    amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10, label="Valor del gasto")
    description = forms.CharField(required=False, label="Detalle", widget=forms.Textarea(attrs={"rows": 2}))
    payment_method = forms.ChoiceField(choices=(), label="Forma de pago", required=False)
    reference = forms.CharField(required=False, label="Referencia")
    transfer_proof = forms.ImageField(required=False, label="Soporte de transferencia")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = [("", "Selecciona")] + list(CashMovementPayment.METHOD_CHOICES)
        self.fields["amount"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "2",
            }
        )
        self.fields["description"].widget.attrs["class"] = "form-control"
        self.fields["payment_method"].widget.attrs["class"] = "form-select"
        self.fields["reference"].widget.attrs["class"] = "form-control"
        self.fields["transfer_proof"].widget.attrs["class"] = "form-control"


class CashDropForm(forms.Form):
    amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10, label="Valor guardado")
    description = forms.CharField(required=False, label="Detalle", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "2",
            }
        )
        self.fields["description"].widget.attrs["class"] = "form-control"
