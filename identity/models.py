from django.conf import settings
from django.db import models


class UserBranchMembership(models.Model):
    ROLE_BRANCH = "sucursal"
    ROLE_EVENT_ADMIN = "evento"
    ROLE_ENTRANCE = "entrada"
    ROLE_BAR = "barra"
    ROLE_CHOICES = [
        (ROLE_BRANCH, "Administrador de sucursal"),
        (ROLE_EVENT_ADMIN, "Administrador de eventos"),
        (ROLE_ENTRANCE, "Personal de entrada"),
        (ROLE_BAR, "Personal de barra"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="branch_memberships")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "branch"], name="identity_membership_user_branch_uniq"),
        ]
        ordering = ["branch__name", "user__username"]
        verbose_name = "Membresia de sucursal"
        verbose_name_plural = "Membresias de sucursal"

    def __str__(self):
        return f"{self.user.username} - {self.branch.name} ({self.get_role_display()})"


class UserEventAssignment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_assignments")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="event_assignments")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="staff_assignments")
    role = models.CharField(max_length=20, choices=UserBranchMembership.ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="identity_assignment_user_event_uniq"),
        ]
        ordering = ["event__starts_at", "user__username"]
        verbose_name = "Asignacion de personal por evento"
        verbose_name_plural = "Asignaciones de personal por evento"

    def __str__(self):
        return f"{self.user.username} - {self.event.name} ({self.get_role_display()})"
