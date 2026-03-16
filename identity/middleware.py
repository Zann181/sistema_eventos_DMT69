from branches.models import Branch, get_principal_branch
from events.application import get_event_choices
from identity.application import build_permission_flags, get_effective_role, get_user_branches, get_user_events_for_branch, is_global_admin


def _resolve_brand_branch(branches):
    for branch in branches:
        if branch.slug == "sucursal-principal":
            return branch
    return Branch.objects.filter(slug="sucursal-principal").first() or get_principal_branch()


def _pick_current_event(events, requested_event_id=None):
    if not events:
        return None
    if requested_event_id:
        for event in events:
            if event.id == requested_event_id:
                return event
    for event in events:
        if event.status == "active":
            return event
    return events[0]


class CurrentBranchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.current_branch = None
        request.current_branch_id = None
        request.current_event = None
        request.available_branches = []
        request.available_events = []
        request.current_role = None
        request.current_permissions = build_permission_flags(getattr(request, "user", None))
        request.brand_branch = None

        if request.user.is_authenticated:
            branches = list(get_user_branches(request.user))
            request.available_branches = branches
            request.brand_branch = _resolve_brand_branch(branches)
            branch = None
            branch_id = request.session.get("current_branch_id")
            if branch_id:
                branch = next((item for item in branches if item.id == branch_id), None)
            if not branch and branches:
                branch = branches[0]
                request.session["current_branch_id"] = branch.id
            if not branch and is_global_admin(request.user):
                branch = Branch.objects.filter(is_active=True).order_by("name").first()
                if branch:
                    request.session["current_branch_id"] = branch.id

            request.current_branch = branch
            request.current_branch_id = getattr(branch, "id", None)
            branch_role = get_effective_role(request.user, branch, None)

            if branch:
                if branch_role in {"admin", "sucursal"}:
                    request.available_events = list(get_event_choices(branch))
                else:
                    request.available_events = list(get_user_events_for_branch(request.user, branch))

                requested_event_id = request.session.get("current_event_id")
                request.current_event = _pick_current_event(request.available_events, requested_event_id)
                if request.current_event:
                    request.session["current_event_id"] = request.current_event.id
                else:
                    request.session.pop("current_event_id", None)

                request.current_role = get_effective_role(request.user, branch, request.current_event)
                request.current_permissions = build_permission_flags(
                    request.user,
                    branch,
                    request.current_event,
                    role=request.current_role,
                )
            else:
                request.current_permissions = build_permission_flags(request.user)

        return self.get_response(request)
