from django.conf import settings
from django.db import migrations


GLOBAL_ADMIN_GROUP = "Administrador Global"


def backfill_event_products(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Event = apps.get_model("events", "Event")
    EventProduct = apps.get_model("sales", "EventProduct")

    events_by_branch = {}
    for event in Event.objects.all().only("id", "branch_id"):
        events_by_branch.setdefault(event.branch_id, []).append(event)

    for product in Product.objects.all().only("id", "branch_id", "price", "is_active", "created_by_id"):
        branch_events = events_by_branch.get(product.branch_id, [])
        for event in branch_events:
            config, created = EventProduct.objects.get_or_create(
                event_id=event.id,
                product_id=product.id,
                defaults={
                    "branch_id": event.branch_id,
                    "is_enabled": bool(product.is_active),
                    "event_price": product.price,
                    "updated_by_id": product.created_by_id,
                },
            )
            updates = []
            if config.branch_id != event.branch_id:
                config.branch_id = event.branch_id
                updates.append("branch")
            if config.event_price is None:
                config.event_price = product.price
                updates.append("event_price")
            if created:
                continue
            if updates:
                config.save(update_fields=updates)


def backfill_cash_roles(apps, schema_editor):
    CashMovement = apps.get_model("sales", "CashMovement")
    UserBranchMembership = apps.get_model("identity", "UserBranchMembership")
    UserEventAssignment = apps.get_model("identity", "UserEventAssignment")
    Group = apps.get_model("auth", "Group")

    global_admin_user_ids = set(
        Group.objects.filter(name=GLOBAL_ADMIN_GROUP).values_list("user__id", flat=True)
    )

    assignment_roles = {
        (row["user_id"], row["branch_id"], row["event_id"]): row["role"]
        for row in UserEventAssignment.objects.filter(is_active=True).values("user_id", "branch_id", "event_id", "role")
    }
    membership_roles = {
        (row["user_id"], row["branch_id"]): row["role"]
        for row in UserBranchMembership.objects.filter(is_active=True).values("user_id", "branch_id", "role")
    }

    for movement in CashMovement.objects.filter(created_role="").exclude(created_by_id=None):
        role = ""
        if movement.created_by_id in global_admin_user_ids:
            role = "admin"
        else:
            role = assignment_roles.get((movement.created_by_id, movement.branch_id, movement.event_id), "")
            if not role:
                role = membership_roles.get((movement.created_by_id, movement.branch_id), "")
        if role:
            movement.created_role = role
            movement.save(update_fields=["created_role"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_alter_product_price"),
        ("events", "0001_initial"),
        ("identity", "0001_initial"),
        ("sales", "0002_cashmovement_created_role_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_event_products, migrations.RunPython.noop),
        migrations.RunPython(backfill_cash_roles, migrations.RunPython.noop),
    ]
