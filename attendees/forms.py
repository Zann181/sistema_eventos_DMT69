from django import forms

from attendees.models import Attendee, Category


class AttendeeForm(forms.ModelForm):
    class Meta:
        model = Attendee
        fields = ["name", "cc", "phone", "email", "category", "paid_amount"]

    def __init__(self, *args, branch=None, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.event = event
        if branch:
            self.fields["category"].queryset = branch.categories.filter(is_active=True)
        else:
            self.fields["category"].queryset = self.fields["category"].queryset.none()
        self.fields["category"].label_from_instance = lambda category: category.name
        for name, field in self.fields.items():
            css_class = "form-select" if name == "category" else "form-control"
            field.widget.attrs["class"] = css_class
        self.fields["name"].label = "Nombre completo"
        self.fields["cc"].label = "Cedula"
        self.fields["phone"].label = "Telefono"
        self.fields["email"].label = "Correo"
        self.fields["category"].label = "Categoria"
        self.fields["phone"].required = True
        self.fields["email"].required = True
        self.fields["paid_amount"].required = False
        self.fields["paid_amount"].label = "Precio pagado"
        self.fields["paid_amount"].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-thousands": "true",
                "data-decimals": "0",
            }
        )

    def clean_cc(self):
        cc = (self.cleaned_data.get("cc") or "").strip()
        if not cc or not self.event:
            return cc

        queryset = Attendee.objects.filter(event=self.event, cc=cc)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Ya existe un asistente con esa cedula en este evento.")
        return cc


class BranchCategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "included_consumptions", "price", "description", "is_active"]
        labels = {
            "name": "Nombre de la categoria",
            "included_consumptions": "Consumiciones incluidas",
            "price": "Precio base",
            "description": "Descripcion",
            "is_active": "Categoria activa",
        }
        widgets = {
            "included_consumptions": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "numeric",
                    "data-thousands": "true",
                    "data-decimals": "0",
                }
            ),
            "price": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "decimal",
                    "data-thousands": "true",
                    "data-decimals": "2",
                }
            ),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.fields["name"].widget.attrs.setdefault("class", "form-control")
        self.fields["is_active"].widget.attrs.setdefault("class", "form-check-input")

    def save(self, commit=True):
        category = super().save(commit=False)
        if self.branch:
            category.branch = self.branch
        if commit:
            category.save()
        return category
