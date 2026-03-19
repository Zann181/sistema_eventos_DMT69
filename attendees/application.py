from django.db import transaction
from django.utils import timezone

from attendees.models import Attendee


@transaction.atomic
def check_in_attendee(attendee, user):
    if attendee.has_checked_in:
        return attendee, False

    attendee.has_checked_in = True
    attendee.checked_in_at = timezone.now()
    attendee.checked_in_by = user
    attendee.save(update_fields=["has_checked_in", "checked_in_at", "checked_in_by"])
    return attendee, True


def get_attendee_for_branch(branch, event, code_or_cc):
    queryset = Attendee.objects.filter(branch=branch, event=event).select_related("category")
    return queryset.filter(qr_code=code_or_cc).first() or queryset.filter(cc=code_or_cc).first()


@transaction.atomic
def delete_branch_category(category):
    if category.attendees.exists():
        if category.is_active:
            category.is_active = False
            category.save(update_fields=["is_active"])
            return "deactivated"
        return "blocked"

    category.delete()
    return "deleted"
