from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from attendees.models import Category
from branches.forms import BranchForm, BranchStaffForm
from attendees.forms import BranchCategoryForm
from branches.models import Branch, get_principal_branch
from identity.application import get_manageable_staff_events, get_user_branches, user_can_manage_branch, user_can_manage_staff
from identity.models import UserBranchMembership, UserEventAssignment


@login_required
def branch_list(request):
    if not user_can_manage_branch(request.user, request.current_branch):
        messages.error(request, "No tienes permisos para administrar sucursales.")
        return redirect("shared_ui:dashboard")
    principal_branch = get_principal_branch()
    branches = Branch.objects.filter(pk=principal_branch.pk) if principal_branch else Branch.objects.none()
    form = BranchForm()
    return render(
        request,
        "branches/list.html",
        {"branches": branches, "form": form, "principal_branch_exists": Branch.objects.exists()},
    )


@login_required
def branch_create(request):
    if not user_can_manage_branch(request.user):
        messages.error(request, "No tienes permisos para crear sucursales.")
        return redirect("shared_ui:dashboard")
    if Branch.objects.exists():
        messages.error(request, "Solo se permite una sucursal principal en el sistema.")
        return redirect("branches:list")

    form = BranchForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        branch = form.save()
        messages.success(request, f"Sucursal {branch.name} creada.")
        return redirect("branches:list")

    return render(
        request,
        "branches/form.html",
        {
            "form": form,
            "title": "Nueva sucursal",
            "active_tab": "general",
            "category_form": BranchCategoryForm(),
            "branch_categories": [],
        },
    )


def _user_is_event_admin_in_branch(user, branch):
    if not user or not branch:
        return False
    if UserBranchMembership.objects.filter(
        user=user,
        branch=branch,
        role=UserBranchMembership.ROLE_EVENT_ADMIN,
        is_active=True,
    ).exists():
        return True
    return UserEventAssignment.objects.filter(
        user=user,
        branch=branch,
        role=UserBranchMembership.ROLE_EVENT_ADMIN,
        is_active=True,
    ).exists()


@login_required
def branch_update(request, slug):
    branch = get_object_or_404(Branch, slug=slug)
    if not (user_can_manage_branch(request.user, branch) or user_can_manage_staff(request.user, branch, getattr(request, "current_event", None))):
        messages.error(request, "No tienes permisos para editar esta sucursal.")
        return redirect("shared_ui:dashboard")

    form_type = request.POST.get("form_type") or request.GET.get("tab") or "general"
    active_tab = form_type if form_type in {"staff", "categories"} else "general"
    if not user_can_manage_branch(request.user, branch):
        active_tab = "staff"
        if form_type != "staff":
            messages.error(request, "Solo tienes acceso a la gestion de personal de tus eventos.")
            return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")
    edit_user_id = request.GET.get("edit_user")
    editing_user = None
    if edit_user_id:
        editing_user = User.objects.filter(pk=edit_user_id).first()
        if editing_user and not user_can_manage_branch(request.user, branch) and _user_is_event_admin_in_branch(editing_user, branch):
            messages.error(request, "No tienes permisos para editar administradores de eventos.")
            return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")
    manageable_events = get_manageable_staff_events(request.user, branch)
    manager_can_assign_admin = user_can_manage_branch(request.user, branch)
    form = BranchForm(instance=branch)
    staff_form = BranchStaffForm(
        branch=branch,
        editing_user=editing_user,
        manageable_events=manageable_events,
        manager_can_assign_admin=manager_can_assign_admin,
    )
    editing_category = branch.categories.filter(pk=request.GET.get("edit_category")).first() if request.GET.get("edit_category") else None
    category_form = BranchCategoryForm(branch=branch, instance=editing_category)

    if request.method == "POST" and form_type == "general":
        if not user_can_manage_branch(request.user, branch):
            messages.error(request, "No tienes permisos para editar la sucursal.")
            return redirect("shared_ui:dashboard")
        form = BranchForm(request.POST, request.FILES, instance=branch)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f"Sucursal {branch.name} actualizada.")
            return redirect("branches:update", slug=branch.slug)
    elif request.method == "POST" and form_type == "staff":
        active_tab = "staff"
        editing_user_id = request.POST.get("user_id")
        if editing_user_id and not user_can_manage_branch(request.user, branch):
            target_user = User.objects.filter(pk=editing_user_id).first()
            if target_user and _user_is_event_admin_in_branch(target_user, branch):
                messages.error(request, "No tienes permisos para editar administradores de eventos.")
                return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")
        staff_form = BranchStaffForm(
            request.POST,
            branch=branch,
            manageable_events=manageable_events,
            manager_can_assign_admin=manager_can_assign_admin,
        )
        if staff_form.is_valid():
            user, assignments, user_created, created_assignments = staff_form.save()
            user_action = "creado" if user_created else "actualizado"
            assignment_action = "creadas" if created_assignments else "actualizadas"
            events_label = ", ".join(assignment.event.name for assignment in assignments) or "todos los eventos de la sucursal principal"
            messages.success(
                request,
                f"Personal {user.username} {user_action}. Asignaciones {assignment_action} para: {events_label}.",
            )
            return redirect("branches:update", slug=branch.slug)
    elif request.method == "POST" and form_type == "categories":
        if not user_can_manage_branch(request.user, branch):
            messages.error(request, "No tienes permisos para administrar categorias.")
            return redirect("shared_ui:dashboard")
        active_tab = "categories"
        editing_category = branch.categories.filter(pk=request.POST.get("category_id")).first() if request.POST.get("category_id") else None
        category_form = BranchCategoryForm(request.POST, branch=branch, instance=editing_category)
        if category_form.is_valid():
            category = category_form.save()
            action_label = "actualizada" if editing_category else "guardada"
            messages.success(request, f"Categoria {category.name} {action_label} para {branch.name}.")
            return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=categories")

    assignments_queryset = UserEventAssignment.objects.filter(branch=branch)
    if not user_can_manage_branch(request.user, branch):
        assignments_queryset = assignments_queryset.filter(event__in=manageable_events).exclude(role=UserBranchMembership.ROLE_EVENT_ADMIN)
    assignments = list(
        assignments_queryset.select_related("user", "event").order_by("user__username", "event__starts_at", "event__name")
    )
    memberships_queryset = UserBranchMembership.objects.filter(branch=branch)
    if not user_can_manage_branch(request.user, branch):
        assignment_user_ids = {assignment.user_id for assignment in assignments}
        memberships_queryset = memberships_queryset.filter(user_id__in=assignment_user_ids).exclude(role=UserBranchMembership.ROLE_EVENT_ADMIN)
    memberships = list(memberships_queryset.select_related("user").order_by("user__username"))
    grouped_staff = {}
    for membership in memberships:
        grouped_staff[membership.user_id] = {
            "user": membership.user,
            "role_display": membership.get_role_display(),
            "is_active": membership.is_active,
            "events": [],
            "has_event_assignments": False,
        }
    for assignment in assignments:
        row = grouped_staff.setdefault(
            assignment.user_id,
            {
                "user": assignment.user,
                "role_display": assignment.get_role_display(),
                "is_active": assignment.is_active,
                "events": [],
                "has_event_assignments": False,
            },
        )
        row["role_display"] = assignment.get_role_display()
        row["is_active"] = row["is_active"] or assignment.is_active
        row["has_event_assignments"] = True
        row["events"].append(
            {
                "name": assignment.event.name,
                "is_active": assignment.is_active,
            }
        )
    staff_rows = list(grouped_staff.values())
    editing_user_events = []
    if editing_user:
        assignments_by_event_id = {
            assignment.event_id: assignment
            for assignment in UserEventAssignment.objects.filter(user=editing_user, branch=branch, event__in=manageable_events).select_related("event")
        }
        for event_item in manageable_events:
            assignment = assignments_by_event_id.get(event_item.id)
            editing_user_events.append(
                {
                    "event": event_item,
                    "assignment": assignment,
                    "is_active": assignment.is_active if assignment else False,
                }
            )
    categories = Category.objects.filter(branch=branch).order_by("name")
    return render(
        request,
        "branches/form.html",
        {
            "form": form,
            "staff_form": staff_form,
            "category_form": category_form,
            "staff_rows": staff_rows,
            "editing_staff_user": editing_user,
            "editing_staff_events": editing_user_events,
            "branch_categories": categories,
            "editing_category": editing_category,
            "title": f"Editar {branch.name}",
            "branch": branch,
            "active_tab": active_tab,
            "staff_management_limited": not user_can_manage_branch(request.user, branch),
        },
    )


@login_required
@require_POST
def branch_assignment_toggle(request, slug, assignment_id):
    branch = get_object_or_404(Branch, slug=slug)
    if not user_can_manage_branch(request.user, branch):
        messages.error(request, "No tienes permisos para administrar esta sucursal.")
        return redirect("shared_ui:dashboard")

    assignment = get_object_or_404(UserEventAssignment, pk=assignment_id, branch=branch)
    assignment.is_active = not assignment.is_active
    assignment.save(update_fields=["is_active", "updated_at"])
    state = "activada" if assignment.is_active else "desactivada"
    messages.success(request, f"Asignacion {state} para {assignment.user.username} en {assignment.event.name}.")
    return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")


@login_required
@require_POST
def branch_staff_event_toggle(request, slug, user_id, event_id):
    branch = get_object_or_404(Branch, slug=slug)
    if not (user_can_manage_branch(request.user, branch) or user_can_manage_staff(request.user, branch, getattr(request, "current_event", None))):
        messages.error(request, "No tienes permisos para administrar esta sucursal.")
        return redirect("shared_ui:dashboard")

    user = get_object_or_404(User, pk=user_id)
    if not user_can_manage_branch(request.user, branch) and _user_is_event_admin_in_branch(user, branch):
        messages.error(request, "No tienes permisos para editar administradores de eventos.")
        return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")
    manageable_events = get_manageable_staff_events(request.user, branch)
    event = get_object_or_404(manageable_events, pk=event_id)
    membership = UserBranchMembership.objects.filter(user=user, branch=branch, is_active=True).first()
    if membership is None:
        messages.error(request, "El usuario no pertenece a esta sucursal.")
        return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff")

    assignment, created = UserEventAssignment.objects.get_or_create(
        user=user,
        branch=branch,
        event=event,
        defaults={"role": membership.role, "is_active": True},
    )
    if not created:
        assignment.is_active = not assignment.is_active
        if assignment.role != membership.role:
            assignment.role = membership.role
            assignment.save(update_fields=["is_active", "role", "updated_at"])
        else:
            assignment.save(update_fields=["is_active", "updated_at"])

    state = "activado" if assignment.is_active else "desactivado"
    messages.success(request, f"Evento {event.name} {state} para {user.username}.")
    return redirect(f"{redirect('branches:update', slug=branch.slug).url}?tab=staff&edit_user={user.id}")


@login_required
def switch_branch(request, branch_id):
    branch = get_object_or_404(Branch, pk=branch_id, is_active=True)
    if not user_can_manage_branch(request.user, branch) and branch not in get_user_branches(request.user):
        messages.error(request, "No puedes acceder a esta sucursal.")
        return redirect("shared_ui:dashboard")

    request.session["current_branch_id"] = branch.id
    request.session.pop("current_event_id", None)
    messages.success(request, f"Sucursal activa: {branch.name}.")
    return redirect(request.META.get("HTTP_REFERER") or "shared_ui:dashboard")
