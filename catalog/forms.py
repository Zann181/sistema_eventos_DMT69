from django import forms

from catalog.models import Product


class ProductForm(forms.ModelForm):
    image = forms.ImageField(required=False)

    class Meta:
        model = Product
        fields = ["name", "description", "image", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "form-control"
        self.fields["description"].widget = forms.Textarea(attrs={"rows": 3, "class": "form-control"})
        self.fields["image"].widget.attrs["class"] = "form-control"
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"
