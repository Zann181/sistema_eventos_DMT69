from django.contrib import messages

from branches.models import Branch
from identity.models import UserBranchMembership, UserEventAssignment


GLOBAL_ADMIN_GROUP = "Administrador Global"


def build_permission_flags(user, branch=None, event=None, role=None):
    effective_role = role if role is not None else get_effective_role(user, branch, event)
    can_manage_branch_configuration = bool(getattr(user, "is_authenticated", False) and is_global_admin(user))
    can_manage_events_configuration = effective_role in {"admin", UserBranchMembership.ROLE_EVENT_ADMIN}
    can_manage_categories_flag = can_manage_events_configuration
    can_access_attendees_flag = effective_role in {
        "admin",
        UserBranchMembership.ROLE_EVENT_ADMIN,
        UserBranchMembership.ROLE_ENTRANCE,
    }
    can_access_sales_flag = effective_role in {
        "admin",
        UserBranchMembership.ROLE_EVENT_ADMIN,
        UserBranchMembership.ROLE_BAR,
    }
    can_access_catalog_flag = effective_role in {"admin", UserBranchMembership.ROLE_EVENT_ADMIN}
    can_switch_context_flag = effective_role in {"admin", UserBranchMembership.ROLE_EVENT_ADMIN}
    return {
        "current_role": effective_role,
        "can_manage_configuration": can_manage_branch_configuration or can_manage_events_configuration,
        "can_manage_branch_configuration": can_manage_branch_configuration,
        "can_manage_events_configuration": can_manage_events_configuration,
        "can_manage_categories": can_manage_categories_flag,
        "can_access_attendees": can_access_attendees_flag,
        "can_access_sales": can_access_sales_flag,
        "can_access_catalog": can_access_catalog_flag,
        "can_switch_context": can_switch_context_flag,
        "can_switch_branch_context": False,
        "can_switch_event_context": can_switch_context_flag,
    }


def is_global_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.groups.filter(name=GLOBAL_ADMIN_GROUP).exists()


def get_user_branches(user):
    if not getattr(user, "is_authenticated", False):
        return Branch.objects.none()
    if is_global_admin(user):
        return Branch.objects.filter(is_active=True)
    return Branch.objects.filter(memberships__user=user, memberships__is_active=True, is_active=True).distinct()


def get_user_membership(user, branch):
    if not getattr(user, "is_authenticated", False) or not branch:
        return None
    return UserBranchMembership.objects.filter(user=user, branch=branch, is_active=True).first()


def user_can_manage_branch(user, branch=None):
    return is_global_admin(user)


def user_can_manage_events(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_manage_events_configuration"]


def user_can_manage_categories(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_manage_categories"]


def user_can_manage_staff(user, branch=None, event=None):
    if is_global_admin(user):
        return True
    if not getattr(user, "is_authenticated", False) or not branch:
        return False
    return UserEventAssignment.objects.filter(
        user=user,
        branch=branch,
        role=UserBranchMembership.ROLE_EVENT_ADMIN,
        is_active=True,
    ).exists()


def require_branch_admin(request, branch=None):
    current_branch = branch or getattr(request, "current_branch", None)
    if not current_branch:
        messages.error(request, "Debes seleccionar una sucursal.")
        return None
    if user_can_manage_branch(request.user, current_branch):
        return current_branch

    messages.error(request, "No tienes permisos para administrar esta sucursal.")
    return None


def ensure_branch_membership(user, branch, role):
    membership, created = UserBranchMembership.objects.get_or_create(
        user=user,
        branch=branch,
        defaults={"role": role, "is_active": True},
    )
    if not created:
        updates = []
        if not membership.is_active:
            membership.is_active = True
            updates.append("is_active")
        if membership.role != role:
            membership.role = role
            updates.append("role")
        if updates:
            membership.save(update_fields=updates)
    return membership


def get_user_event_assignment(user, branch, event):
    if not getattr(user, "is_authenticated", False) or not branch or not event:
        return None
    return UserEventAssignment.objects.filter(
        user=user,
        branch=branch,
        event=event,
        is_active=True,
    ).first()


def get_effective_role(user, branch=None, event=None):
    if not getattr(user, "is_authenticated", False):
        return None
    if is_global_admin(user):
        return "admin"

    assignment = get_user_event_assignment(user, branch, event)
    if assignment:
        return assignment.role

    membership = get_user_membership(user, branch)
    return membership.role if membership else None


def user_can_access_attendees(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_access_attendees"]


def user_can_access_sales(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_access_sales"]


def user_can_access_catalog(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_access_catalog"]


def get_user_events_for_branch(user, branch):
    from events.models import Event

    if not getattr(user, "is_authenticated", False) or not branch:
        return Event.objects.none()
    if user_can_manage_branch(user, branch):
        return Event.objects.filter(branch=branch).order_by("-starts_at")
    event_ids = UserEventAssignment.objects.filter(user=user, branch=branch, is_active=True).values_list("event_id", flat=True)
    return Event.objects.filter(id__in=event_ids, branch=branch).order_by("-starts_at")


def get_manageable_staff_events(user, branch):
    from events.models import Event

    if not getattr(user, "is_authenticated", False) or not branch:
        return Event.objects.none()
    if user_can_manage_branch(user, branch):
        return Event.objects.filter(branch=branch).order_by("-starts_at", "name")
    event_ids = UserEventAssignment.objects.filter(
        user=user,
        branch=branch,
        role=UserBranchMembership.ROLE_EVENT_ADMIN,
        is_active=True,
    ).values_list("event_id", flat=True)
    if event_ids:
        return Event.objects.filter(branch=branch, id__in=event_ids).order_by("-starts_at", "name")
    return Event.objects.none()


def user_can_switch_context(user, branch=None, event=None):
    return build_permission_flags(user, branch, event)["can_switch_context"]
