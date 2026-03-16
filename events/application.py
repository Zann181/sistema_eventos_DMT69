from events.models import Event


def get_event_choices(branch):
    if not branch:
        return Event.objects.none()
    return Event.objects.filter(branch=branch).order_by("-starts_at")
