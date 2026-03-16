from django import forms

from catalog.models import Product


class ProductForm(forms.ModelForm):
    image = forms.ImageField(required=True)

    class Meta:
        model = Product
        fields = ["name", "description", "image", "price", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price"].widget = forms.TextInput(
            attrs={
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "0",
            }
        )
