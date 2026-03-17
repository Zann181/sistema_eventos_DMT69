from django.contrib.auth.models import User
from django import forms

from branches.models import Branch
from events.models import Event
from identity.application import ensure_branch_membership
from identity.models import UserBranchMembership, UserEventAssignment
from shared_ui.validators import validate_png_upload


class BranchForm(forms.ModelForm):
    def clean_logo(self):
        return validate_png_upload(self.cleaned_data.get("logo"), field_label="logo de la sucursal")

    class Meta:
        model = Branch
        fields = [
            "name",
            "slug",
            "code_prefix",
            "primary_color",
            "secondary_color",
            "page_background_color",
            "surface_color",
            "panel_color",
            "contact_email",
            "contact_phone",
            "logo",
            "is_active",
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "secondary_color": forms.TextInput(attrs={"type": "color"}),
            "page_background_color": forms.TextInput(attrs={"type": "color"}),
            "surface_color": forms.TextInput(attrs={"type": "color"}),
            "panel_color": forms.TextInput(attrs={"type": "color"}),
            "logo": forms.ClearableFileInput(attrs={"accept": ".png,image/png"}),
        }
        labels = {
            "name": "Nombre de la sucursal",
            "slug": "Identificador URL",
            "code_prefix": "Prefijo de codigos",
            "primary_color": "Color principal",
            "secondary_color": "Color secundario",
            "page_background_color": "Color de fondo de pagina",
            "surface_color": "Color de fondo de tarjetas",
            "panel_color": "Color de fondos secundarios",
            "contact_email": "Correo de contacto",
            "contact_phone": "Telefono de contacto",
            "logo": "Logo de la sucursal",
            "is_active": "Sucursal activa",
        }
        help_texts = {
            "code_prefix": "Se usa en codigos QR y consecutivos de la sucursal.",
            "logo": "Este logo se usa en la interfaz y en el inicio de sesion cuando la sucursal principal esta activa. Solo PNG.",
            "page_background_color": "Controla el color base del fondo general de la pagina.",
            "surface_color": "Se usa en tarjetas y contenedores principales.",
            "panel_color": "Se usa en fondos secundarios como previews o bloques suaves.",
        }


class BranchStaffForm(forms.Form):
    user_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    username = forms.CharField(max_length=150, label="Usuario")
    first_name = forms.CharField(max_length=150, required=False, label="Nombre")
    last_name = forms.CharField(max_length=150, required=False, label="Apellido")
    email = forms.EmailField(required=False, label="Correo")
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="Contrasena",
        help_text="Obligatoria solo para usuarios nuevos. Si la llenas, actualiza la contrasena del usuario existente.",
    )
    events = forms.ModelMultipleChoiceField(
        queryset=Event.objects.none(),
        label="Eventos con acceso",
        widget=forms.CheckboxSelectMultiple,
    )
    role = forms.ChoiceField(choices=UserBranchMembership.ROLE_CHOICES, label="Rol")
    is_active = forms.BooleanField(required=False, initial=True, label="Asignacion activa")

    def __init__(self, *args, branch=None, manageable_events=None, manager_can_assign_admin=False, **kwargs):
        editing_user = kwargs.pop("editing_user", None)
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.editing_user = editing_user
        self.manager_can_assign_admin = manager_can_assign_admin
        self.fields["role"].choices = [
            choice
            for choice in UserBranchMembership.ROLE_CHOICES
            if choice[0] != UserBranchMembership.ROLE_BRANCH
            and (manager_can_assign_admin or choice[0] != UserBranchMembership.ROLE_EVENT_ADMIN)
        ]
        if manageable_events is None:
            manageable_events = branch.events.order_by("-starts_at", "name") if branch else Event.objects.none()
        self.fields["events"].queryset = manageable_events
        self.fields["events"].widget.choices = self.fields["events"].choices
        self.fields["events"].label_from_instance = lambda event: f"{event.name}"
        self.fields["events"].help_text = "Puedes marcar uno o varios eventos para este usuario."
        if editing_user or (self.is_bound and self.data.get("user_id")):
            self.fields["username"].widget.attrs["readonly"] = True
        if editing_user and not self.is_bound:
            active_assignments = list(
                UserEventAssignment.objects.filter(user=editing_user, branch=branch, is_active=True).select_related("event")
            )
            membership = UserBranchMembership.objects.filter(user=editing_user, branch=branch).first()
            role = active_assignments[0].role if active_assignments else getattr(membership, "role", "")
            self.initial.update(
                {
                    "user_id": editing_user.id,
                    "username": editing_user.username,
                    "first_name": editing_user.first_name,
                    "last_name": editing_user.last_name,
                    "email": editing_user.email,
                    "role": role,
                    "events": [assignment.event_id for assignment in active_assignments],
                    "is_active": any(assignment.is_active for assignment in active_assignments) or getattr(membership, "is_active", True),
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username", "").strip()
        password = cleaned_data.get("password")
        role = cleaned_data.get("role")
        user_id = cleaned_data.get("user_id")
        if not username:
            return cleaned_data

        user = None
        if user_id:
            user = User.objects.filter(pk=user_id).first()
            if not user:
                self.add_error(None, "El usuario que intentas editar ya no existe.")
                return cleaned_data
            cleaned_data["username"] = user.username
        else:
            user = User.objects.filter(username=username).first()
        if not user and not password:
            self.add_error("password", "Debes definir una contrasena para crear el usuario.")
        if role == UserBranchMembership.ROLE_BRANCH:
            self.add_error("role", "El administrador de sucursal es exclusivo del super admin.")
        if role == UserBranchMembership.ROLE_EVENT_ADMIN and not self.manager_can_assign_admin:
            self.add_error("role", "Solo el super admin puede asignar administradores de eventos.")

        events = cleaned_data.get("events") or []
        if not events:
            self.add_error("events", "Debes seleccionar al menos un evento.")
        if self.branch:
            for event in events:
                if event.branch_id != self.branch.id:
                    self.add_error("events", "Todos los eventos seleccionados deben pertenecer a esta sucursal.")
                    break
        return cleaned_data

    def save(self):
        data = self.cleaned_data
        user_id = data.get("user_id")
        created = False
        if user_id:
            user = User.objects.get(pk=user_id)
        else:
            user, created = User.objects.get_or_create(
                username=data["username"].strip(),
                defaults={
                    "first_name": data.get("first_name", ""),
                    "last_name": data.get("last_name", ""),
                    "email": data.get("email", ""),
                },
            )

        updated_fields = []
        for field in ["first_name", "last_name", "email"]:
            new_value = data.get(field, "")
            if new_value != getattr(user, field):
                setattr(user, field, new_value)
                updated_fields.append(field)
        if not user.is_active:
            user.is_active = True
            updated_fields.append("is_active")
        if updated_fields:
            user.save(update_fields=updated_fields)

        if data.get("password"):
            user.set_password(data["password"])
            user.save(update_fields=["password"])

        selected_event_ids = {event.id for event in data["events"]}
        assignments = []
        created_assignments = 0
        existing_assignments = UserEventAssignment.objects.filter(
            user=user,
            branch=self.branch,
            role=data["role"],
        )
        for assignment in existing_assignments.exclude(event_id__in=selected_event_ids):
            if assignment.is_active:
                assignment.is_active = False
                assignment.save(update_fields=["is_active", "updated_at"])

        for event in data["events"]:
            assignment, created_assignment = UserEventAssignment.objects.update_or_create(
                user=user,
                event=event,
                defaults={
                    "branch": self.branch,
                    "role": data["role"],
                    "is_active": data.get("is_active", True),
                },
            )
            assignments.append(assignment)
            if created_assignment:
                created_assignments += 1

        ensure_branch_membership(user, self.branch, data["role"])
        return user, assignments, created, created_assignments
