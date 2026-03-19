from decimal import Decimal
from io import BytesIO
from pathlib import Path
import email.policy
import smtplib
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from attendees.models import Attendee, Category
from branches.models import Branch
from events.forms import EventForm
from catalog.models import Product
from events.models import Event
from identity.models import UserBranchMembership, UserEventAssignment
from media_assets.models import MediaAsset
from sales.application import create_cash_movement, process_sale, process_sale_cart
from sales.models import BarSale, CashMovement, EventProduct
from ticketing.application import build_event_share_text, send_attendee_ticket_email
from django.test.utils import override_settings


def make_test_image(name="image.png", color="#c44536"):
    image = Image.new("RGB", (32, 32), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_test_jpeg(name="image.jpg", color="#c44536"):
    image = Image.new("RGB", (32, 32), color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class BootstrapAndRepoTests(TestCase):
    def test_global_admin_group_bootstraps_after_migrate(self):
        self.assertTrue(Group.objects.filter(name="Administrador Global").exists())

    def test_runtime_does_not_register_legacy_apps(self):
        self.assertNotIn("core", settings.INSTALLED_APPS)
        self.assertNotIn("ticketing", settings.INSTALLED_APPS)

    def test_legacy_route_is_not_exposed(self):
        response = self.client.get("/legacy/")

        self.assertEqual(response.status_code, 404)

    def test_login_page_renders_without_any_branch(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ZANN EVENT")

    def test_branch_list_renders_without_current_branch(self):
        group, _ = Group.objects.get_or_create(name="Administrador Global")
        user = User.objects.create_user(username="admin-empty", password="12345678")
        user.groups.add(group)
        self.assertTrue(self.client.login(username="admin-empty", password="12345678"))

        response = self.client.get(reverse("branches:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aun no existe la sucursal principal.")

    def test_dashboard_renders_without_current_branch_or_event(self):
        group, _ = Group.objects.get_or_create(name="Administrador Global")
        user = User.objects.create_user(username="admin-dashboard-empty", password="12345678")
        user.groups.add(group)
        self.assertTrue(self.client.login(username="admin-dashboard-empty", password="12345678"))

        response = self.client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configura una sucursal")
        self.assertContains(response, "Selecciona o crea un evento para empezar a operar.")

    def test_gitignore_excludes_generated_local_artifacts(self):
        content = Path(settings.BASE_DIR / ".gitignore").read_text(encoding="utf-8")

        for entry in ("__pycache__/", "*.py[cod]", "media/", "staticfiles/", ".vscode/", "certs/"):
            self.assertIn(entry, content)


class ModularArchitectureTests(TestCase):
    def setUp(self):
        self.group, _ = Group.objects.get_or_create(name="Administrador Global")
        self.user = User.objects.create_user(username="operador", password="12345678")
        self.user.groups.add(self.group)
        self.branch = Branch.objects.create(name="Sucursal Norte", slug="sucursal-norte", code_prefix="NOR")
        self.other_branch = Branch.objects.create(name="Sucursal Sur", slug="sucursal-sur", code_prefix="SUR")
        self.event = Event.objects.create(
            branch=self.branch,
            name="Evento Norte",
            slug="evento-norte",
            starts_at="2026-03-13T20:00:00Z",
            ends_at="2026-03-14T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="NOR",
            email_subject="Acceso confirmado para {attendee_name} en {event_name}",
            email_preheader="Preview editable del evento",
            email_warning_text="Ingreso Early editable para el correo.",
            email_qr_title="Tu QR queda adjunto en este correo",
        )
        self.other_event = Event.objects.create(
            branch=self.other_branch,
            name="Evento Sur",
            slug="evento-sur",
            starts_at="2026-03-13T20:00:00Z",
            ends_at="2026-03-14T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="SUR",
        )
        UserBranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BRANCH,
            is_active=True,
        )
        self.category = Category.objects.create(branch=self.branch, name="VIP", included_consumptions=2, price=50000)
        self.attendee = Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=self.category,
            name="Motaz",
            cc="123",
            phone="300",
            email="motaz@test.com",
            has_checked_in=True,
            included_balance=2,
        )

    def test_login_page_sets_csrf_cookie_and_disables_cache(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-cache", response["Cache-Control"])

    def test_login_with_invalid_csrf_uses_friendly_failure_view(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("login"))

        response = client.post(
            reverse("login"),
            {
                "username": "operador",
                "password": "12345678",
                "csrfmiddlewaretoken": "token-invalido",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Tu sesion o el formulario expiraron.", status_code=403)
        self.assertContains(
            response,
            "Accede para operar sucursales, eventos, entrada y barra desde un mismo panel.",
            status_code=403,
        )

    def test_product_image_is_normalized_to_webp_and_asset_is_registered(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Cerveza",
            description="Lata",
            image=make_test_image(),
            price=12000,
            created_by=self.user,
        )

        self.assertTrue(product.image.name.endswith(".webp"))
        self.assertTrue(MediaAsset.objects.filter(kind="product_image", object_id=product.id).exists())

    def test_attendee_qr_uses_event_logo_overlay(self):
        self.event.logo = make_test_image("event-logo.png", color="#ff0000")
        self.event.qr_fill_color = "#000000"
        self.event.qr_background_color = "#ffffff"
        self.event.save()

        attendee = Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=self.category,
            name="QR Logo",
            cc="777",
            email="qr-logo@test.com",
        )

        attendee.qr_image.open("rb")
        with Image.open(attendee.qr_image) as qr_image:
            center_pixel = qr_image.convert("RGB").getpixel((qr_image.width // 2, qr_image.height // 2))

        self.assertGreater(center_pixel[0], 180)

    def test_whatsapp_share_page_and_card_are_available(self):
        share_response = self.client.get(reverse("attendees:whatsapp_share", args=[self.attendee.qr_code]))
        self.assertEqual(share_response.status_code, 200)
        self.assertContains(share_response, "og:image")

        card_response = self.client.get(reverse("attendees:whatsapp_card", args=[self.attendee.qr_code]))
        self.assertEqual(card_response.status_code, 200)
        self.assertEqual(card_response["Content-Type"], "image/png")

        self.assertTrue(self.client.login(username="operador", password="12345678"))
        session = self.client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        qr_file_response = self.client.get(reverse("attendees:whatsapp_qr_file", args=[self.attendee.qr_code]))
        self.assertEqual(qr_file_response.status_code, 200)
        self.assertEqual(qr_file_response["Content-Type"], "image/png")

        flyer_response = self.client.get(reverse("attendees:whatsapp_flyer_file", args=[self.attendee.qr_code]))
        self.assertIn(flyer_response.status_code, {200, 404})

    def test_whatsapp_flyer_file_uses_webp_response_when_flyer_exists(self):
        self.event.flyer = make_test_image("flyer-share.png", color="#00aa55")
        self.event.save()

        self.assertTrue(self.client.login(username="operador", password="12345678"))
        session = self.client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = self.client.get(reverse("attendees:whatsapp_flyer_file", args=[self.attendee.qr_code]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")

    def test_process_sale_uses_event_price_without_touching_product_inventory(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Agua",
            image=make_test_image("agua.png", color="#1d3557"),
            price=6000,
            created_by=self.user,
        )
        event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=5500,
            updated_by=self.user,
        )

        sale = process_sale(
            branch=self.branch,
            event=self.event,
            event_product=event_product,
            quantity=2,
            user=self.user,
            attendee=self.attendee,
            use_included_balance=True,
        )

        product.refresh_from_db()
        self.attendee.refresh_from_db()

        self.assertEqual(sale.total, 11000)
        self.assertEqual(self.attendee.included_balance, 0)

    def test_sale_create_accepts_cart_with_multiple_products(self):
        first_product = Product.objects.create(
            branch=self.branch,
            name="Corona",
            image=make_test_image("corona.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        second_product = Product.objects.create(
            branch=self.branch,
            name="Red Bull",
            image=make_test_image("redbull.png", color="#1d3557"),
            price=15000,
            created_by=self.user,
        )
        first_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=first_product,
            is_enabled=True,
            event_price=15000,
            updated_by=self.user,
        )
        second_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=second_product,
            is_enabled=True,
            event_price=15000,
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("sales:create"),
            {
                "sale_cart": (
                    f'[{{"event_product_id":"{first_event_product.id}","quantity":1}},'
                    f'{{"event_product_id":"{second_event_product.id}","quantity":2}}]'
                ),
                "sale_payment_method_1": "efectivo",
                "sale_payment_amount_1": "45.000",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(BarSale.objects.filter(branch=self.branch, event=self.event).count(), 2)
        self.assertEqual(
            sum(payment.amount for sale in BarSale.objects.filter(branch=self.branch, event=self.event) for payment in sale.payments.all()),
            45000,
        )

    def test_sale_create_accepts_cash_overpayment_and_stores_net_total(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Ron caja",
            image=make_test_image("ron-caja.png", color="#7d4f50"),
            price=95000,
            created_by=self.user,
        )
        event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=95000,
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("sales:create"),
            {
                "sale_cart": f'[{{"event_product_id":"{event_product.id}","quantity":1}}]',
                "sale_payment_method_1": "efectivo",
                "sale_payment_amount_1": "100.000",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        sale = BarSale.objects.get(branch=self.branch, event=self.event, product=product)
        self.assertEqual(sale.total, 95000)
        self.assertEqual(sale.payments.count(), 1)
        self.assertEqual(sale.payments.first().amount, 95000)

    def test_sales_list_shows_rows_and_allows_delete(self):
        first_product = Product.objects.create(
            branch=self.branch,
            name="Corona delete",
            image=make_test_image("corona-delete.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        second_product = Product.objects.create(
            branch=self.branch,
            name="Red Bull delete",
            image=make_test_image("redbull-delete.png", color="#1d3557"),
            price=12000,
            created_by=self.user,
        )
        first_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=first_product,
            is_enabled=True,
            event_price=15000,
            updated_by=self.user,
        )
        second_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=second_product,
            is_enabled=True,
            event_price=12000,
            updated_by=self.user,
        )
        sales = process_sale_cart(
            branch=self.branch,
            event=self.event,
            user=self.user,
            items=[
                {"event_product_id": str(first_event_product.id), "quantity": 2},
                {"event_product_id": str(second_event_product.id), "quantity": 1},
            ],
            payments=[{"method": "efectivo", "amount": Decimal("42000")}],
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("sales:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tabla de ventas")
        self.assertContains(response, "Corona delete")
        self.assertContains(response, "Red Bull delete")
        self.assertContains(response, "Eliminar")

        delete_response = client.post(reverse("sales:delete", args=[sales[0].id]), follow=True)

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(BarSale.objects.filter(sale_group=sales[0].sale_group).exists())

    def test_sales_pos_hides_product_description_text(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Sin copy",
            description="Texto que no debe verse en caja",
            image=make_test_image("sin-copy.png", color="#1d3557"),
            price=12000,
            created_by=self.user,
        )
        EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=12000,
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("sales:pos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Texto que no debe verse en caja")
        self.assertNotContains(response, "Sin descripcion")

    def test_sales_event_products_modal_shows_actions_and_integer_price_input(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Corona modal",
            image=make_test_image("corona-modal.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=Decimal("15000.00"),
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("sales:pos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar")
        self.assertContains(response, "Eliminar")
        self.assertContains(response, 'value="15000"')
        self.assertNotContains(response, 'value="15000.00"')

    def test_new_global_products_require_event_configuration_before_sale(self):
        Product.objects.create(
            branch=self.branch,
            name="Producto legado",
            image=make_test_image("producto-legado.png", color="#336699"),
            price=22000,
            created_by=self.user,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("sales:pos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Producto legado")
        self.assertEqual(list(response.context["sale_products"]), [])
        self.assertTrue(
            EventProduct.objects.filter(
                branch=self.branch,
                event=self.event,
                product__name="Producto legado",
                is_enabled=False,
                event_price__isnull=True,
            ).exists()
        )

    def test_sales_product_create_redirects_to_event_configuration_without_price(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("sales:product_create"),
            {
                "name": "Nuevo global",
                "description": "Producto sin precio global",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(name="Nuevo global")
        event_product = EventProduct.objects.get(branch=self.branch, event=self.event, product=product)
        self.assertEqual(product.price, Decimal("0"))
        self.assertFalse(event_product.is_enabled)
        self.assertIsNone(event_product.event_price)
        self.assertContains(response, "Configura el precio del evento para habilitarlo.")

    def test_event_admin_can_open_product_modal_and_create_product(self):
        event_admin = User.objects.create_user(username="evento-admin-producto", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="evento-admin-producto", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        pos_response = client.get(f"{reverse('sales:pos')}?action=productos")

        self.assertEqual(pos_response.status_code, 200)
        self.assertContains(pos_response, "Agregar producto")
        self.assertContains(pos_response, 'id="salesProductModal"', html=False)

        create_response = client.post(
            reverse("sales:product_create"),
            {
                "name": "Producto evento admin",
                "description": "Creado por admin de evento",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(create_response.status_code, 200)
        product = Product.objects.get(name="Producto evento admin")
        event_product = EventProduct.objects.get(branch=self.branch, event=self.event, product=product)
        self.assertFalse(event_product.is_enabled)
        self.assertIsNone(event_product.event_price)
        self.assertContains(create_response, "Configura el precio del evento para habilitarlo.")

    def test_bar_role_can_open_pos_with_products_action_without_modal_rendered(self):
        bar_user = User.objects.create_user(username="barra-action", password="12345678@")
        UserBranchMembership.objects.create(
            user=bar_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=bar_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="barra-action", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(f"{reverse('sales:pos')}?action=productos")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="salesProductModal"', html=False)

    def test_sales_product_delete_keeps_history_by_retiring_product(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Ron retiro",
            image=make_test_image("ron-retiro.png", color="#7d4f50"),
            price=80000,
            created_by=self.user,
        )
        event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=80000,
            updated_by=self.user,
        )
        process_sale_cart(
            branch=self.branch,
            event=self.event,
            user=self.user,
            items=[{"event_product_id": str(event_product.id), "quantity": 1}],
            payments=[{"method": "efectivo", "amount": Decimal("80000")}],
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(reverse("sales:product_delete", args=[product.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        event_product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertFalse(event_product.is_enabled)
        self.assertTrue(BarSale.objects.filter(product=product, branch=self.branch, event=self.event).exists())

    def test_dashboard_context_for_super_admin_includes_available_branches(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_branch"], self.branch)
        self.assertIn(self.branch, list(response.context["available_branches"]))
        self.assertIn("dashboard_summary", response.context)
        self.assertIn("entrada_analytics", response.context)
        self.assertIn("barra_analytics", response.context)
        self.assertIn("combined_analytics", response.context)
        self.assertContains(response, "dashboard-donut")

    def test_branch_staff_tab_creates_event_assignments_and_event_admin_role(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        second_branch_event = Event.objects.create(
            branch=self.branch,
            name="Evento Norte 2",
            slug="evento-norte-2",
            starts_at="2026-03-14T20:00:00Z",
            ends_at="2026-03-15T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="NOR2",
        )

        response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "staff",
                "username": "entrada1",
                "password": "12345678@",
                "first_name": "Ana",
                "last_name": "Entrada",
                "email": "ana@test.com",
                "events": [self.event.id, second_branch_event.id],
                "role": UserBranchMembership.ROLE_EVENT_ADMIN,
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="entrada1").exists())
        self.assertTrue(
            UserEventAssignment.objects.filter(
                branch=self.branch,
                event=self.event,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                user__username="entrada1",
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            UserEventAssignment.objects.filter(
                branch=self.branch,
                event=second_branch_event,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                user__username="entrada1",
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            UserBranchMembership.objects.filter(
                branch=self.branch,
                user__username="entrada1",
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                is_active=True,
            ).exists()
        )

    def test_branch_staff_tab_lists_membership_only_users(self):
        membership_only_user = User.objects.create_user(username="barra-sin-evento", password="12345678@")
        UserBranchMembership.objects.create(
            user=membership_only_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "barra-sin-evento")
        self.assertContains(response, "Sin eventos asignados")

    def test_branch_staff_tab_renders_events_as_checkboxes(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="checkbox"', html=False)
        self.assertContains(response, "Puedes marcar uno o varios eventos para este usuario.")
        self.assertNotContains(response, 'multiple', html=False)

    def test_branch_staff_edit_prefills_existing_user(self):
        editable_user = User.objects.create_user(
            username="editar-personal",
            password="12345678@",
            first_name="Laura",
            last_name="Barra",
            email="laura@test.com",
        )
        UserBranchMembership.objects.create(
            user=editable_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=editable_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff&edit_user={editable_user.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="editar-personal"', html=False)
        self.assertContains(response, 'readonly', html=False)
        self.assertContains(response, "Guardar cambios")
        self.assertContains(response, "Eventos disponibles para editar-personal")
        self.assertContains(response, self.event.name)

    def test_branch_staff_save_updates_branch_membership_role(self):
        existing_user = User.objects.create_user(username="cambio-rol", password="12345678@")
        UserBranchMembership.objects.create(
            user=existing_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "staff",
                "username": "cambio-rol",
                "password": "",
                "first_name": "",
                "last_name": "",
                "email": "",
                "events": [self.event.id],
                "role": UserBranchMembership.ROLE_EVENT_ADMIN,
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserBranchMembership.objects.filter(
                user=existing_user,
                branch=self.branch,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                is_active=True,
            ).exists()
        )

    def test_branch_staff_edit_updates_existing_user_by_user_id(self):
        editable_user = User.objects.create_user(
            username="editar-id",
            password="12345678@",
            first_name="Nombre",
            last_name="Viejo",
            email="viejo@test.com",
        )
        second_event = Event.objects.create(
            branch=self.branch,
            name="Evento Norte 3",
            slug="evento-norte-3",
            starts_at="2026-03-16T20:00:00Z",
            ends_at="2026-03-17T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="NOR3",
        )
        UserBranchMembership.objects.create(
            user=editable_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=editable_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "staff",
                "user_id": editable_user.id,
                "username": "editar-id",
                "password": "",
                "first_name": "Nombre",
                "last_name": "Nuevo",
                "email": "nuevo@test.com",
                "events": [second_event.id],
                "role": UserBranchMembership.ROLE_EVENT_ADMIN,
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        editable_user.refresh_from_db()
        self.assertEqual(editable_user.last_name, "Nuevo")
        self.assertEqual(editable_user.email, "nuevo@test.com")
        self.assertTrue(
            UserEventAssignment.objects.filter(
                user=editable_user,
                branch=self.branch,
                event=second_event,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                is_active=True,
            ).exists()
        )

    def test_branch_staff_event_toggle_creates_and_disables_assignment(self):
        editable_user = User.objects.create_user(username="toggle-evento", password="12345678@")
        second_event = Event.objects.create(
            branch=self.branch,
            name="Evento Norte 4",
            slug="evento-norte-4",
            starts_at="2026-03-18T20:00:00Z",
            ends_at="2026-03-19T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="NOR4",
        )
        UserBranchMembership.objects.create(
            user=editable_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        activate_response = client.post(
            reverse("branches:staff_event_toggle", args=[self.branch.slug, editable_user.id, second_event.id]),
            follow=True,
        )
        self.assertEqual(activate_response.status_code, 200)
        self.assertTrue(
            UserEventAssignment.objects.filter(
                user=editable_user,
                branch=self.branch,
                event=second_event,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                is_active=True,
            ).exists()
        )

        deactivate_response = client.post(
            reverse("branches:staff_event_toggle", args=[self.branch.slug, editable_user.id, second_event.id]),
            follow=True,
        )
        self.assertEqual(deactivate_response.status_code, 200)
        self.assertTrue(
            UserEventAssignment.objects.filter(
                user=editable_user,
                branch=self.branch,
                event=second_event,
                role=UserBranchMembership.ROLE_EVENT_ADMIN,
                is_active=False,
            ).exists()
        )

    def test_branch_staff_delete_removes_branch_access_without_deleting_history(self):
        removable_user = User.objects.create_user(username="remover-personal", password="12345678@")
        UserBranchMembership.objects.create(
            user=removable_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=removable_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.post(
            reverse("branches:staff_delete", args=[self.branch.slug, removable_user.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        removable_user.refresh_from_db()
        self.assertFalse(removable_user.is_active)
        self.assertFalse(UserBranchMembership.objects.filter(user=removable_user, branch=self.branch).exists())
        self.assertFalse(UserEventAssignment.objects.filter(user=removable_user, branch=self.branch).exists())
        self.assertNotContains(response, f"?tab=staff&edit_user={removable_user.id}", html=False)

    def test_branch_categories_are_managed_at_branch_level_and_used_in_attendee_form(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "categories",
                "name": "General",
                "included_consumptions": "3",
                "price": "35000",
                "description": "Categoria base",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(branch=self.branch, name="General").exists())

        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        attendee_response = client.get(reverse("attendees:list"))
        category_names = list(attendee_response.context["form"].fields["category"].queryset.values_list("name", flat=True))
        self.assertIn("General", category_names)

    def test_event_day_form_defaults_to_dia_category(self):
        dia_category = Category.objects.create(
            branch=self.branch,
            name="Dia",
            included_consumptions=0,
            price=40000,
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        event_day_form = response.context["event_day_form"]
        self.assertEqual(str(event_day_form["category"].value()), str(dia_category.pk))
        self.assertEqual(str(event_day_form["unit_amount"].value()), "40000.00")

    def test_attendees_list_does_not_render_dashboard_panel(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertNotContains(response, "Vista interactiva del evento")
        self.assertNotContains(response, "dashboard-donut")

    def test_attendees_list_shows_whatsapp_action_per_row(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertContains(response, "data-whatsapp-share")
        self.assertContains(response, "fa-whatsapp")
        self.assertContains(response, "aria-label=\"Enviar por WhatsApp\"")

    def test_attendees_list_uses_email_column_instead_of_balance_and_ingreso_columns(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertContains(response, "<th>Correo</th>", html=True)
        self.assertNotContains(response, "<th>Balance</th>", html=True)
        self.assertNotContains(response, "<th>Ingreso</th>", html=True)

    def test_payment_breakdown_rows_can_be_removed_in_entry_and_bar_modules(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Agua remove",
            image=make_test_image("agua-remove.png", color="#1d3557"),
            price=6000,
            created_by=self.user,
        )
        EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=5500,
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        attendees_response = client.get(reverse("attendees:list"))
        sales_response = client.get(reverse("sales:pos"))

        self.assertContains(attendees_response, "data-remove-payment-row")
        self.assertContains(sales_response, "data-remove-payment-row")
        self.assertContains(attendees_response, "Eliminar")
        self.assertContains(sales_response, "Eliminar")

    def test_payment_breakdown_defaults_first_method_to_cash(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Agua cash default",
            image=make_test_image("agua-cash-default.png", color="#1d3557"),
            price=6000,
            created_by=self.user,
        )
        EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=5500,
            updated_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        attendees_response = client.get(reverse("attendees:list"))
        sales_response = client.get(reverse("sales:pos"))

        self.assertContains(attendees_response, '<option value="efectivo" selected>Efectivo</option>', html=True)
        self.assertContains(sales_response, '<option value="efectivo" selected>Efectivo</option>', html=True)

    def test_check_in_endpoint_rejects_attendee_from_other_branch(self):
        other_category = Category.objects.create(branch=self.other_branch, name="General", included_consumptions=0, price=10000)
        outsider = Attendee.objects.create(
            branch=self.other_branch,
            event=self.other_event,
            category=other_category,
            name="Invitado Sur",
            cc="999",
            qr_code="SUR-SUR-INVITADO",
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))

        response = client.post(reverse("attendees:check_in"), {"code": outsider.qr_code}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_attendee_entry_dashboard_restores_scanner_list_and_create_tabs(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scanner QR")
        self.assertContains(response, "Lista asistentes")
        self.assertContains(response, "Nuevo asistente")
        self.assertNotContains(response, "Analitica de acceso")

    def test_category_create_returns_to_new_attendee_and_selects_new_category(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:category_create"),
            {
                "name": "Lanzamiento",
                "included_consumptions": "2",
                "price": "55000",
                "description": "Nueva categoria",
                "is_active": "on",
                "return_tab": "crear",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        category = Category.objects.get(branch=self.branch, name="Lanzamiento")
        self.assertContains(response, 'data-initial-tab="crear"', html=False)
        self.assertNotContains(response, 'data-open-modal="categorias"', html=False)
        self.assertEqual(str(response.context["form"]["category"].value()), str(category.pk))
        self.assertEqual(str(response.context["form"]["paid_amount"].value()), "55000.00")

    def test_category_create_errors_keep_new_attendee_tab_and_reopen_modal(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:category_create"),
            {
                "name": "",
                "included_consumptions": "1",
                "price": "10000",
                "description": "",
                "is_active": "on",
                "return_tab": "crear",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'data-initial-tab="crear"', html=False, status_code=400)
        self.assertContains(response, 'data-open-modal="categorias"', html=False, status_code=400)

    def test_category_update_preserves_existing_attendee_values(self):
        attendee = Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=self.category,
            name="Categoria fija",
            cc="CAT-1",
            phone="300",
            email="cat@test.com",
            paid_amount=Decimal("50000"),
            included_balance=2,
            created_by=self.user,
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:category_update", args=[self.category.id]),
            {
                "name": "VIP editada",
                "included_consumptions": "5",
                "price": "65000",
                "description": "Categoria actualizada",
                "is_active": "on",
                "return_tab": "crear",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        attendee.refresh_from_db()
        self.assertEqual(self.category.name, "VIP editada")
        self.assertEqual(self.category.price, Decimal("65000"))
        self.assertEqual(attendee.paid_amount, Decimal("50000"))
        self.assertEqual(attendee.included_balance, 2)

    def test_category_update_errors_keep_modal_open(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:category_update", args=[self.category.id]),
            {
                "name": "",
                "included_consumptions": "1",
                "price": "10000",
                "description": "",
                "is_active": "on",
                "return_tab": "crear",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Editar categoria", status_code=400)
        self.assertContains(response, 'data-open-modal="categorias"', html=False, status_code=400)

    def test_catalog_category_create_works_for_admin(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("catalog:category_create"),
            {
                "name": "Backstage",
                "included_consumptions": "3",
                "price": "70000",
                "description": "Categoria administrada desde catalogo",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(branch=self.branch, name="Backstage").exists())
        self.assertContains(response, "Categorias de acceso")

    def test_branch_role_can_manage_catalog_crud_from_list(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Ron",
            description="Botella",
            created_by=self.user,
        )
        EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=Decimal("90000"),
            updated_by=self.user,
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        list_response = client.get(reverse("catalog:list"))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Categorias de acceso")
        self.assertContains(list_response, "Guardar producto")
        self.assertContains(list_response, "Ron")

        update_response = client.post(
            reverse("catalog:product_update", args=[product.id]),
            {
                "name": "Ron anejo",
                "description": "Botella premium",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(update_response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.name, "Ron anejo")
        self.assertContains(update_response, "Producto Ron anejo actualizado.")

    def test_catalog_category_delete_deactivates_when_attendees_exist(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("catalog:category_delete", args=[self.category.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertFalse(self.category.is_active)
        self.assertContains(response, "inactivada porque ya tiene asistentes asociados")

    def test_dashboard_shows_access_analytics_only_there(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen general")
        self.assertContains(response, "Entrada")
        self.assertContains(response, "Barra")
        self.assertContains(response, "Ingresos por modulo")
        self.assertContains(response, "Ventas por producto")
        self.assertContains(response, "dashboard-pie-chart")
        self.assertContains(response, "dashboard-donut-detail")

    def test_cash_movements_capture_role_snapshot_and_dashboard_breakdown(self):
        expense = create_cash_movement(
            branch=self.branch,
            event=self.event,
            user=self.user,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_EXPENSE,
            total_amount=Decimal("15000"),
            description="Hielo",
            payments=[{"method": "efectivo", "amount": Decimal("15000")}],
        )
        create_cash_movement(
            branch=self.branch,
            event=self.event,
            user=self.user,
            module=CashMovement.MODULE_ENTRANCE,
            movement_type=CashMovement.TYPE_CASH_DROP,
            total_amount=Decimal("30000"),
            description="Retiro puerta",
        )

        self.assertEqual(expense.created_role, "admin")

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        breakdown = response.context["dashboard_summary"]["movement_breakdown"]
        self.assertTrue(any(row["created_role"] == "admin" and row["module"] == "barra" for row in breakdown))
        self.assertContains(response, "Gastos y vaciados por operador")

    def test_dashboard_separates_manual_and_event_day_income_without_double_counting(self):
        manual_category = Category.objects.create(
            branch=self.branch,
            name="General",
            included_consumptions=0,
            price=35000,
        )
        Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=manual_category,
            name="Manual",
            cc="MAN-1",
            phone="301",
            email="manual@test.com",
            origin=Attendee.ORIGIN_MANUAL,
            paid_amount=Decimal("50000"),
            created_by=self.user,
        )
        create_cash_movement(
            branch=self.branch,
            event=self.event,
            user=self.user,
            module=CashMovement.MODULE_ENTRANCE,
            movement_type=CashMovement.TYPE_EVENT_DAY,
            total_amount=Decimal("80000"),
            description="Puerta",
            payments=[
                {"method": "efectivo", "amount": Decimal("50000")},
                {"method": "qr", "amount": Decimal("30000")},
            ],
            attendee_quantity=2,
            unit_amount=Decimal("40000"),
        )
        Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=manual_category,
            name="Puerta 1",
            cc="PUERTA-1",
            origin=Attendee.ORIGIN_EVENT_DAY,
            has_checked_in=True,
            created_by=self.user,
        )
        Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=manual_category,
            name="Puerta 2",
            cc="PUERTA-2",
            origin=Attendee.ORIGIN_EVENT_DAY,
            has_checked_in=True,
            created_by=self.user,
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        entrance_metrics = response.context["entrada_analytics"]["metrics"]
        self.assertEqual(entrance_metrics["manual_income"], Decimal("50000"))
        self.assertEqual(entrance_metrics["event_day_income"], Decimal("80000"))
        self.assertEqual(entrance_metrics["income_total"], Decimal("130000"))

    def test_dashboard_shows_bar_sales_totals_and_top_product(self):
        first_product = Product.objects.create(
            branch=self.branch,
            name="Corona",
            image=make_test_image("corona-bar.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        second_product = Product.objects.create(
            branch=self.branch,
            name="Red Bull",
            image=make_test_image("redbull-bar.png", color="#1d3557"),
            price=20000,
            created_by=self.user,
        )
        first_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=first_product,
            is_enabled=True,
            event_price=15000,
            updated_by=self.user,
        )
        second_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=second_product,
            is_enabled=True,
            event_price=20000,
            updated_by=self.user,
        )

        process_sale(
            branch=self.branch,
            event=self.event,
            event_product=first_event_product,
            quantity=3,
            user=self.user,
            payments=[{"method": "efectivo", "amount": Decimal("45000")}],
        )
        process_sale(
            branch=self.branch,
            event=self.event,
            event_product=second_event_product,
            quantity=1,
            user=self.user,
            payments=[{"method": "tarjeta", "amount": Decimal("20000")}],
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        bar_metrics = response.context["barra_analytics"]["metrics"]
        self.assertEqual(bar_metrics["income_total"], Decimal("65000"))
        self.assertEqual(bar_metrics["units_sold"], 4)
        self.assertEqual(bar_metrics["top_units_product_name"], "Corona")
        self.assertEqual(bar_metrics["top_units_product_units"], 3)
        self.assertEqual(bar_metrics["top_revenue_product_name"], "Corona")
        self.assertEqual(bar_metrics["top_revenue_product_total"], Decimal("45000"))
        payment_labels = [row["label"] for row in response.context["barra_analytics"]["payment_methods"]]
        self.assertIn("Efectivo", payment_labels)
        self.assertIn("Tarjeta", payment_labels)

    def test_event_product_effective_price_uses_event_price_only(self):
        product = Product.objects.create(
            branch=self.branch,
            name="Corona normalizada",
            image=make_test_image("corona-normalizada.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=product,
            is_enabled=True,
            event_price=Decimal("15000"),
            updated_by=self.user,
        )

        self.assertEqual(event_product.effective_price, Decimal("15000"))

    def test_dashboard_bar_analytics_updates_after_invoice_delete(self):
        first_product = Product.objects.create(
            branch=self.branch,
            name="Corona dashboard delete",
            image=make_test_image("corona-dashboard-delete.png", color="#f4b942"),
            price=15000,
            created_by=self.user,
        )
        second_product = Product.objects.create(
            branch=self.branch,
            name="Red Bull dashboard delete",
            image=make_test_image("redbull-dashboard-delete.png", color="#1d3557"),
            price=12000,
            created_by=self.user,
        )
        first_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=first_product,
            is_enabled=True,
            event_price=15000,
            updated_by=self.user,
        )
        second_event_product = EventProduct.objects.create(
            branch=self.branch,
            event=self.event,
            product=second_product,
            is_enabled=True,
            event_price=12000,
            updated_by=self.user,
        )
        sales = process_sale_cart(
            branch=self.branch,
            event=self.event,
            user=self.user,
            items=[
                {"event_product_id": str(first_event_product.id), "quantity": 1},
                {"event_product_id": str(second_event_product.id), "quantity": 2},
            ],
            payments=[{"method": "efectivo", "amount": Decimal("39000")}],
        )

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        before_delete = client.get(reverse("shared_ui:dashboard"))
        self.assertContains(before_delete, "Corona dashboard delete")
        self.assertContains(before_delete, "Red Bull dashboard delete")
        self.assertEqual(before_delete.context["barra_analytics"]["metrics"]["income_total"], Decimal("39000"))

        delete_response = client.post(reverse("sales:delete", args=[sales[0].id]), follow=True)
        self.assertEqual(delete_response.status_code, 200)

        after_delete = client.get(reverse("shared_ui:dashboard"))
        self.assertEqual(after_delete.context["barra_analytics"]["metrics"]["income_total"], Decimal("0"))
        self.assertEqual(after_delete.context["barra_analytics"]["metrics"]["units_sold"], 0)
        self.assertNotContains(after_delete, "Corona dashboard delete")
        self.assertNotContains(after_delete, "Red Bull dashboard delete")

    def test_attendee_check_in_preview_and_confirm_flow(self):
        pending = Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=self.category,
            name="Pendiente",
            cc="555",
            phone="312",
            email="pendiente@test.com",
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        preview = client.post(
            reverse("attendees:check_in_preview"),
            data='{"codigo": "%s"}' % pending.qr_code,
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["success"])
        self.assertEqual(preview.json()["attendee"]["name"], "Pendiente")

        confirm = client.post(
            reverse("attendees:confirm_check_in"),
            data='{"codigo": "%s"}' % pending.qr_code,
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(confirm.json()["success"])

        pending.refresh_from_db()
        self.assertTrue(pending.has_checked_in)

    def test_global_admin_can_delete_checked_in_attendee(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:delete"),
            data='{"cc": "%s"}' % self.attendee.cc,
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(Attendee.objects.filter(pk=self.attendee.pk).exists())

    def test_entrance_role_cannot_delete_checked_in_attendee(self):
        checked_in_attendee = Attendee.objects.create(
            branch=self.branch,
            event=self.event,
            category=self.category,
            name="Ingreso protegido",
            cc="556",
            phone="313",
            email="protegido@test.com",
            has_checked_in=True,
        )
        entrance = User.objects.create_user(username="entrada-delete", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada-delete", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:delete"),
            data='{"cc": "%s"}' % checked_in_attendee.cc,
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["message"], "No se puede eliminar un asistente que ya ingreso.")
        self.assertTrue(Attendee.objects.filter(pk=checked_in_attendee.pk).exists())

    def test_attendee_create_rejects_duplicate_cc_in_same_event_with_form_error(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:create"),
            {
                "name": "Duplicado",
                "cc": self.attendee.cc,
                "phone": "301",
                "email": "duplicado@test.com",
                "category": self.category.id,
                "paid_amount": "50000",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Ya existe un asistente con esa cedula en este evento.", status_code=400)

    def test_entrance_role_cannot_create_category_from_attendees_module(self):
        entrance = User.objects.create_user(username="entrada-cat", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada-cat", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:category_create"),
            {
                "name": "Taquilla",
                "included_consumptions": "1",
                "price": "30000",
                "description": "Venta en puerta",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Category.objects.filter(branch=self.branch, name="Taquilla").exists())
        self.assertContains(response, "Solo los administradores pueden gestionar categorias.")

    def test_branch_role_can_update_and_delete_entrance_expense(self):
        movement = create_cash_movement(
            branch=self.branch,
            event=self.event,
            user=self.user,
            module=CashMovement.MODULE_ENTRANCE,
            movement_type=CashMovement.TYPE_EXPENSE,
            total_amount=Decimal("20000"),
            description="Gasto inicial",
            payments=[{"method": "efectivo", "amount": Decimal("20000")}],
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        list_response = client.get(f"{reverse('attendees:list')}?tab=gastos")

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Gasto inicial")

        update_response = client.post(
            reverse("attendees:expense_update", args=[movement.id]),
            {
                "amount": "20000",
                "description": "Gasto actualizado",
            },
            follow=True,
        )

        self.assertEqual(update_response.status_code, 200)
        movement.refresh_from_db()
        self.assertEqual(movement.description, "Gasto actualizado")

        delete_response = client.post(
            reverse("attendees:expense_delete", args=[movement.id]),
            follow=True,
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(CashMovement.objects.filter(pk=movement.id).exists())

    def test_branch_role_can_update_and_delete_bar_cash_drop(self):
        movement = create_cash_movement(
            branch=self.branch,
            event=self.event,
            user=self.user,
            module=CashMovement.MODULE_BAR,
            movement_type=CashMovement.TYPE_CASH_DROP,
            total_amount=Decimal("35000"),
            description="Retiro inicial",
        )
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        list_response = client.get(f"{reverse('sales:pos')}?action=vaciar-caja")

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Vaciados registrados")
        self.assertContains(list_response, "Retiro inicial")

        update_response = client.post(
            reverse("sales:cash_drop_update", args=[movement.id]),
            {
                "amount": "42000",
                "description": "Retiro actualizado",
            },
            follow=True,
        )

        self.assertEqual(update_response.status_code, 200)
        movement.refresh_from_db()
        self.assertEqual(movement.total_amount, Decimal("42000"))
        self.assertEqual(movement.description, "Retiro actualizado")

        delete_response = client.post(
            reverse("sales:cash_drop_delete", args=[movement.id]),
            follow=True,
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(CashMovement.objects.filter(pk=movement.id).exists())

    def test_attendees_category_crud_shortcuts_are_hidden_for_entrance_role(self):
        entrance = User.objects.create_user(username="entrada-crud", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada-crud", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "CRUD categorias")

    def test_entrance_role_sees_only_dashboard_and_entrada_menu(self):
        entrance = User.objects.create_user(username="entrada1", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada1", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Scanner QR")
        self.assertContains(response, "Lista asistentes")
        self.assertContains(response, "Nuevo asistente")
        self.assertContains(response, "Dia de evento")
        self.assertContains(response, "Gastos")
        self.assertContains(response, "Vaciar caja")
        self.assertNotContains(response, "Barra")
        self.assertNotContains(response, "Catalogo")
        self.assertNotContains(response, "Sucursales")
        self.assertNotContains(response, "Eventos")
        self.assertNotContains(response, "Personal")
        self.assertNotContains(response, "Sucursal activa")
        self.assertNotContains(response, "Evento activo")

    def test_entrance_role_cannot_open_bar_or_configuration(self):
        entrance = User.objects.create_user(username="entrada2", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada2", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        sales_response = client.get(reverse("sales:pos"), follow=True)
        branch_response = client.get(reverse("branches:list"), follow=True)

        self.assertEqual(sales_response.status_code, 200)
        self.assertEqual(branch_response.status_code, 200)
        self.assertContains(sales_response, "No tienes permisos para acceder al modulo de barra.")
        self.assertContains(branch_response, "No tienes permisos para administrar sucursales.")

    def test_entrance_role_cannot_switch_to_unassigned_event(self):
        extra_event = Event.objects.create(
            branch=self.branch,
            name="Evento Extra",
            slug="evento-extra",
            starts_at="2026-03-15T20:00:00Z",
            ends_at="2026-03-16T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="EXT",
        )
        entrance = User.objects.create_user(username="entrada3", password="12345678@")
        UserBranchMembership.objects.create(
            user=entrance,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=entrance,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="entrada3", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("events:switch", args=[extra_event.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No puedes acceder a este evento.")

    def test_branch_role_sees_shared_barra_submenu_actions(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Punto de venta")
        self.assertContains(response, "Agregar producto")
        self.assertContains(response, "Productos del evento")
        self.assertContains(response, "Vaciar caja")

    def test_second_branch_creation_is_blocked(self):
        global_admin = User.objects.create_superuser(username="global-root", password="12345678@", email="root@test.com")
        client = Client()
        self.assertTrue(client.login(username="global-root", password="12345678@"))

        response = client.post(
            reverse("branches:create"),
            {
                "name": "Otra sucursal",
                "slug": "otra-sucursal",
                "code_prefix": "OTR",
                "primary_color": "#111111",
                "secondary_color": "#222222",
                "page_background_color": "#333333",
                "surface_color": "#444444",
                "panel_color": "#555555",
                "contact_email": "",
                "contact_phone": "",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solo se permite una sucursal principal en el sistema.")
        self.assertFalse(Branch.objects.filter(slug="otra-sucursal").exists())

    def test_superuser_sees_django_admin_link_in_sidebar(self):
        superuser = User.objects.create_superuser(
            username="super-sidebar",
            password="12345678@",
            email="super-sidebar@test.com",
        )
        client = Client()
        self.assertTrue(client.login(username="super-sidebar", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Django")
        self.assertContains(response, reverse("admin:index"))

    def test_event_admin_only_sees_assigned_events_and_not_branch_configuration(self):
        event_admin = User.objects.create_user(username="evento-admin", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="evento-admin", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        dashboard_response = client.get(reverse("shared_ui:dashboard"))
        events_response = client.get(reverse("events:list"))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "Eventos")
        self.assertContains(dashboard_response, "Agregar producto")
        self.assertContains(dashboard_response, "Productos del evento")
        self.assertContains(dashboard_response, "Catalogo")
        self.assertNotContains(dashboard_response, "Sucursales")
        self.assertContains(dashboard_response, "Personal")

        self.assertEqual(events_response.status_code, 200)
        staff_response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff")
        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, self.event.name)
        self.assertNotContains(staff_response, 'option value="evento"', html=False)

    def test_event_admin_can_create_staff_only_for_allowed_events(self):
        event_admin = User.objects.create_user(username="evento-admin-staff", password="12345678@")
        other_event = Event.objects.create(
            branch=self.branch,
            name="Evento ajeno",
            slug="evento-ajeno",
            starts_at="2026-03-20T20:00:00Z",
            ends_at="2026-03-21T06:00:00Z",
            status=Event.STATUS_ACTIVE,
            qr_prefix="OTRO",
        )
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-admin-staff", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        allowed_response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "staff",
                "username": "entrada-evento",
                "password": "12345678@",
                "first_name": "Entrada",
                "last_name": "Evento",
                "email": "entrada-evento@test.com",
                "events": [self.event.id],
                "role": UserBranchMembership.ROLE_ENTRANCE,
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(allowed_response.status_code, 200)
        self.assertTrue(
            UserEventAssignment.objects.filter(
                user__username="entrada-evento",
                branch=self.branch,
                event=self.event,
                role=UserBranchMembership.ROLE_ENTRANCE,
                is_active=True,
            ).exists()
        )

        denied_response = client.post(
            reverse("branches:update", args=[self.branch.slug]),
            {
                "form_type": "staff",
                "username": "entrada-denegada",
                "password": "12345678@",
                "first_name": "Entrada",
                "last_name": "Denegada",
                "email": "entrada-denegada@test.com",
                "events": [other_event.id],
                "role": UserBranchMembership.ROLE_ENTRANCE,
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(denied_response.status_code, 200)
        self.assertContains(denied_response, "Debes seleccionar al menos un evento.")
        self.assertFalse(User.objects.filter(username="entrada-denegada").exists())

    def test_event_admin_can_delete_staff_from_managed_event(self):
        event_admin = User.objects.create_user(username="evento-admin-delete", password="12345678@")
        removable_user = User.objects.create_user(username="entrada-borrable", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserBranchMembership.objects.create(
            user=removable_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=removable_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_ENTRANCE,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-admin-delete", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("branches:staff_delete", args=[self.branch.slug, removable_user.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        removable_user.refresh_from_db()
        self.assertFalse(removable_user.is_active)
        self.assertFalse(UserBranchMembership.objects.filter(user=removable_user, branch=self.branch).exists())
        self.assertFalse(UserEventAssignment.objects.filter(user=removable_user, branch=self.branch).exists())
        self.assertContains(response, "Acceso de entrada-borrable eliminado de tus eventos administrados.")

    def test_event_admin_staff_tab_shows_events_even_with_old_branch_membership_role(self):
        event_admin = User.objects.create_user(username="evento-admin-legado", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-admin-legado", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.name)
        self.assertNotContains(response, "No hay eventos disponibles todavia.")

    def test_event_admin_does_not_see_other_event_admins_in_staff_table(self):
        event_admin = User.objects.create_user(username="evento-admin-visible", password="12345678@")
        other_admin = User.objects.create_user(username="evento-admin-oculto", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserBranchMembership.objects.create(
            user=other_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=other_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-admin-visible", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "evento-admin-oculto")
        self.assertNotContains(response, "Administrador de eventos")

    def test_event_admin_cannot_edit_other_event_admin(self):
        event_admin = User.objects.create_user(username="evento-admin-editor", password="12345678@")
        other_admin = User.objects.create_user(username="evento-admin-bloqueado", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserBranchMembership.objects.create(
            user=other_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=other_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-admin-editor", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(
            f"{reverse('branches:update', args=[self.branch.slug])}?tab=staff&edit_user={other_admin.id}",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No tienes permisos para editar administradores de eventos.")
        self.assertNotContains(response, f'value="{other_admin.username}"', html=False)

    def test_event_admin_can_open_catalog_and_create_global_product(self):
        event_admin = User.objects.create_user(username="evento-admin-catalogo", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="evento-admin-catalogo", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        list_response = client.get(reverse("catalog:list"))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Categorias de acceso")
        self.assertContains(list_response, "Configurar evento")
        self.assertContains(list_response, self.event.name)

        create_response = client.post(
            reverse("catalog:create"),
            {
                "name": "Catalogo evento admin",
                "description": "Creado desde catalogo",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(create_response.status_code, 200)
        product = Product.objects.get(name="Catalogo evento admin")
        event_product = EventProduct.objects.get(branch=self.branch, event=self.event, product=product)
        self.assertFalse(event_product.is_enabled)
        self.assertIsNone(event_product.event_price)
        self.assertContains(create_response, "Configura el precio del evento para habilitarlo.")

    def test_bar_role_sees_same_barra_submenu_actions(self):
        bar_user = User.objects.create_user(username="barra-menu", password="12345678@")
        UserBranchMembership.objects.create(
            user=bar_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=bar_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="barra-menu", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("shared_ui:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Punto de venta")
        self.assertNotContains(response, "Agregar producto")
        self.assertNotContains(response, "Productos del evento")
        self.assertContains(response, "Vaciar caja")

    def test_event_form_rejects_non_png_logo(self):
        form = EventForm(
            data={
                "name": self.event.name,
                "slug": self.event.slug,
                "description": self.event.description,
                "starts_at": "2026-03-13T15:00",
                "ends_at": "2026-03-13T15:00",
                "status": Event.STATUS_ACTIVE,
                "qr_prefix": self.event.qr_prefix,
                "access_policy": "",
                "email_subject": self.event.email_subject,
                "email_preheader": self.event.email_preheader,
                "email_heading": self.event.email_heading,
                "email_intro": self.event.email_intro,
                "email_message_title": self.event.email_message_title,
                "email_body": self.event.email_body,
                "email_warning_title": self.event.email_warning_title,
                "email_warning_text": self.event.email_warning_text,
                "email_details_title": self.event.email_details_title,
                "email_date_text": self.event.email_date_text,
                "email_time_text": self.event.email_time_text,
                "venue_name": self.event.venue_name,
                "maps_url": "",
                "maps_label": self.event.maps_label,
                "dress_code": self.event.dress_code,
                "email_qr_title": self.event.email_qr_title,
                "email_qr_note": self.event.email_qr_note,
                "email_footer": self.event.email_footer,
                "email_closing_text": self.event.email_closing_text,
                "email_team_signature": self.event.email_team_signature,
                "email_legal_note": self.event.email_legal_note,
                "email_background_color": self.event.email_background_color,
                "email_card_color": self.event.email_card_color,
                "email_header_background_color": self.event.email_header_background_color,
                "email_text_color": self.event.email_text_color,
                "email_muted_text_color": self.event.email_muted_text_color,
                "email_accent_color": self.event.email_accent_color,
                "email_border_color": self.event.email_border_color,
                "email_section_background_color": self.event.email_section_background_color,
                "email_warning_background_color": self.event.email_warning_background_color,
                "qr_fill_color": self.event.qr_fill_color,
                "qr_background_color": self.event.qr_background_color,
                "qr_logo_background_color": self.event.qr_logo_background_color,
                "qr_logo_scale": self.event.qr_logo_scale,
            },
            files={"logo": make_test_jpeg()},
            instance=self.event,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)

    def test_event_form_accepts_create_without_hidden_end_and_status_fields(self):
        form = EventForm(
            data={
                "name": "Evento Nuevo",
                "slug": "evento-nuevo",
                "description": "Demo",
                "starts_at": "2026-03-20T21:00",
                "qr_prefix": "NEW",
                "access_policy": "",
                "email_subject": "Asunto",
                "email_preheader": "Preheader",
                "email_heading": "Heading",
                "email_intro": "Intro",
                "email_message_title": "Titulo",
                "email_body": "Body",
                "email_warning_title": "Warn",
                "email_warning_text": "Warn text",
                "email_details_title": "Detalles",
                "email_date_text": "Fecha",
                "email_time_text": "Hora",
                "venue_name": "Lugar",
                "maps_url": "",
                "maps_label": "Mapa",
                "dress_code": "Negro",
                "email_qr_title": "QR",
                "email_qr_note": "Nota",
                "email_footer": "Footer",
                "email_closing_text": "Cierre",
                "email_team_signature": "Firma",
                "email_legal_note": "Legal",
                "email_background_color": "#f6f2eb",
                "email_card_color": "#ffffff",
                "email_header_background_color": "#111315",
                "email_text_color": "#172121",
                "email_muted_text_color": "#bdbdbd",
                "email_accent_color": "#c44536",
                "email_border_color": "#1f1f22",
                "email_section_background_color": "#18191b",
                "email_warning_background_color": "#2a1c17",
                "qr_fill_color": "#102542",
                "qr_background_color": "#f8f9fa",
                "qr_logo_background_color": "#ffffff",
                "qr_logo_scale": "4",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ends_at"], form.cleaned_data["starts_at"])
        self.assertEqual(form.cleaned_data["status"], Event.STATUS_ACTIVE)

    def test_event_update_view_shows_existing_asset_preview(self):
        self.event.logo = make_test_image("event-logo.png")
        self.event.flyer = make_test_image("event-flyer.png")
        self.event.save()

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("events:update", args=[self.event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Logo actual")
        self.assertContains(response, "Flyer actual")
        self.assertNotContains(response, "Logo exclusivo del QR")

    def test_event_create_view_renders_without_existing_assets(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session.save()

        response = client.get(reverse("events:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-file-preview-card="logo"', html=False)
        self.assertContains(response, "Cuando cargues una imagen, aparecera aqui en tiempo real.")

    def test_event_create_view_persists_and_redirects(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("events:create"),
            {
                "name": "Evento Nuevo Vista",
                "slug": "evento-nuevo-vista",
                "description": "Demo",
                "starts_at": "2026-03-20T21:00",
                "qr_prefix": "NEW",
                "access_policy": "",
                "email_subject": "Asunto",
                "email_preheader": "Preheader",
                "email_heading": "Heading",
                "email_intro": "Intro",
                "email_message_title": "Titulo",
                "email_body": "Body",
                "email_warning_title": "Warn",
                "email_warning_text": "Warn text",
                "email_details_title": "Detalles",
                "email_date_text": "Fecha",
                "email_time_text": "Hora",
                "venue_name": "Lugar",
                "maps_url": "",
                "maps_label": "Mapa",
                "dress_code": "Negro",
                "email_qr_title": "QR",
                "email_qr_note": "Nota",
                "email_footer": "Footer",
                "email_closing_text": "Cierre",
                "email_team_signature": "Firma",
                "email_legal_note": "Legal",
                "email_background_color": "#f6f2eb",
                "email_card_color": "#ffffff",
                "email_header_background_color": "#111315",
                "email_text_color": "#172121",
                "email_muted_text_color": "#bdbdbd",
                "email_accent_color": "#c44536",
                "email_border_color": "#1f1f22",
                "email_section_background_color": "#18191b",
                "email_warning_background_color": "#2a1c17",
                "qr_fill_color": "#102542",
                "qr_background_color": "#f8f9fa",
                "qr_logo_background_color": "#ffffff",
                "qr_logo_scale": "4",
            },
        )

        created_event = Event.objects.get(branch=self.branch, slug="evento-nuevo-vista")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("events:update", args=[created_event.id]))

    def test_event_admin_can_create_event_in_current_branch(self):
        event_admin = User.objects.create_user(username="evento-creador", password="12345678@")
        UserBranchMembership.objects.create(
            user=event_admin,
            branch=self.branch,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=event_admin,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_EVENT_ADMIN,
            is_active=True,
        )

        client = Client()
        self.assertTrue(client.login(username="evento-creador", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("events:create"),
            {
                "name": "Evento Admin Branch",
                "slug": "evento-admin-branch",
                "description": "Demo",
                "starts_at": "2026-03-21T21:00",
                "qr_prefix": "EAB",
                "access_policy": "",
                "email_subject": "Asunto",
                "email_preheader": "Preheader",
                "email_heading": "Heading",
                "email_intro": "Intro",
                "email_message_title": "Titulo",
                "email_body": "Body",
                "email_warning_title": "Warn",
                "email_warning_text": "Warn text",
                "email_details_title": "Detalles",
                "email_date_text": "Fecha",
                "email_time_text": "Hora",
                "venue_name": "Lugar",
                "maps_url": "",
                "maps_label": "Mapa",
                "dress_code": "Negro",
                "email_qr_title": "QR",
                "email_qr_note": "Nota",
                "email_footer": "Footer",
                "email_closing_text": "Cierre",
                "email_team_signature": "Firma",
                "email_legal_note": "Legal",
                "email_background_color": "#f6f2eb",
                "email_card_color": "#ffffff",
                "email_header_background_color": "#111315",
                "email_text_color": "#172121",
                "email_muted_text_color": "#bdbdbd",
                "email_accent_color": "#c44536",
                "email_border_color": "#1f1f22",
                "email_section_background_color": "#18191b",
                "email_warning_background_color": "#2a1c17",
                "qr_fill_color": "#102542",
                "qr_background_color": "#f8f9fa",
                "qr_logo_background_color": "#ffffff",
                "qr_logo_scale": "4",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(branch=self.branch, slug="evento-admin-branch").exists())

    def test_attendees_list_renders_when_checked_in_user_is_missing(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.get(reverse("attendees:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "N/A")

    def test_event_media_is_normalized_to_webp_and_preserved_on_update(self):
        self.event.logo = make_test_image("event-logo.png")
        self.event.flyer = make_test_image("event-flyer.png")
        self.event.save()
        self.event.refresh_from_db()

        self.assertTrue(self.event.logo.name.endswith(".png"))
        self.assertTrue(self.event.flyer.name.endswith(".webp"))

        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("events:update", args=[self.event.id]),
            {
                "name": self.event.name,
                "slug": self.event.slug,
                "description": self.event.description,
                "starts_at": "2026-03-13T15:00",
                "ends_at": "2026-03-13T15:00",
                "status": Event.STATUS_ACTIVE,
                "qr_prefix": self.event.qr_prefix,
                "access_policy": self.event.access_policy,
                "email_subject": self.event.email_subject,
                "email_preheader": self.event.email_preheader,
                "email_heading": self.event.email_heading,
                "email_intro": self.event.email_intro,
                "email_message_title": self.event.email_message_title,
                "email_body": self.event.email_body,
                "email_warning_title": self.event.email_warning_title,
                "email_warning_text": self.event.email_warning_text,
                "email_details_title": self.event.email_details_title,
                "email_date_text": self.event.email_date_text,
                "email_time_text": self.event.email_time_text,
                "venue_name": self.event.venue_name,
                "maps_url": self.event.maps_url,
                "maps_label": self.event.maps_label,
                "dress_code": self.event.dress_code,
                "email_qr_title": self.event.email_qr_title,
                "email_qr_note": self.event.email_qr_note,
                "email_footer": self.event.email_footer,
                "email_closing_text": self.event.email_closing_text,
                "email_team_signature": self.event.email_team_signature,
                "email_legal_note": self.event.email_legal_note,
                "email_background_color": self.event.email_background_color,
                "email_card_color": self.event.email_card_color,
                "email_header_background_color": self.event.email_header_background_color,
                "email_text_color": self.event.email_text_color,
                "email_muted_text_color": self.event.email_muted_text_color,
                "email_accent_color": self.event.email_accent_color,
                "email_border_color": self.event.email_border_color,
                "email_section_background_color": self.event.email_section_background_color,
                "email_warning_background_color": self.event.email_warning_background_color,
                "qr_fill_color": self.event.qr_fill_color,
                "qr_background_color": self.event.qr_background_color,
                "qr_logo_background_color": self.event.qr_logo_background_color,
                "qr_logo_scale": self.event.qr_logo_scale,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertTrue(self.event.logo.name.endswith(".png"))
        self.assertTrue(self.event.flyer.name.endswith(".webp"))

    def test_event_day_registration_creates_checked_in_attendees_and_split_payments(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:event_day_create"),
            {
                "category": self.category.id,
                "attendee_quantity": "2",
                "unit_amount": "40000",
                "description": "Puerta",
                "event_day_payment_method_1": "efectivo",
                "event_day_payment_amount_1": "50000",
                "event_day_payment_method_2": "qr",
                "event_day_payment_amount_2": "30000",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        movement = CashMovement.objects.get(movement_type=CashMovement.TYPE_EVENT_DAY)
        self.assertEqual(movement.total_amount, 80000)
        self.assertEqual(movement.attendee_quantity, 2)
        self.assertEqual(movement.payments.count(), 2)
        event_day_attendees = Attendee.objects.filter(
            branch=self.branch,
            event=self.event,
            has_checked_in=True,
            created_by=self.user,
        )
        self.assertEqual(event_day_attendees.count(), 2)
        self.assertEqual(
            event_day_attendees.filter(origin=Attendee.ORIGIN_EVENT_DAY).count(),
            2,
        )

    def test_bar_module_can_register_expense(self):
        bar_user = User.objects.create_user(username="barra1", password="12345678@")
        UserBranchMembership.objects.create(
            user=bar_user,
            branch=self.branch,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        UserEventAssignment.objects.create(
            user=bar_user,
            branch=self.branch,
            event=self.event,
            role=UserBranchMembership.ROLE_BAR,
            is_active=True,
        )
        client = Client()
        self.assertTrue(client.login(username="barra1", password="12345678@"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("sales:expense_create"),
            {
                "amount": "25000",
                "description": "Compra de hielo",
                "payment_method": "efectivo",
                "reference": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        movement = CashMovement.objects.get(movement_type=CashMovement.TYPE_EXPENSE, module=CashMovement.MODULE_BAR)
        self.assertEqual(movement.total_amount, 25000)
        self.assertEqual(movement.payments.count(), 1)

    def test_attendee_expense_create_accepts_split_payments(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:expense_create"),
            {
                "amount": "25000",
                "description": "Gasto mixto",
                "expense_payment_method_1": "efectivo",
                "expense_payment_amount_1": "10000",
                "expense_payment_reference_1": "",
                "expense_payment_method_2": "transferencia",
                "expense_payment_amount_2": "15000",
                "expense_payment_reference_2": "TRX-1",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        movement = CashMovement.objects.get(movement_type=CashMovement.TYPE_EXPENSE, module=CashMovement.MODULE_ENTRANCE)
        self.assertEqual(movement.total_amount, 25000)
        self.assertEqual(movement.payments.count(), 2)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_attendee_ticket_email_uses_editable_event_content(self):
        self.event.flyer = make_test_image("flyer.png", color="#00ff00")
        self.event.qr_background_color = "#000000"
        self.event.save()
        sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Preview editable del evento", mail.outbox[0].alternatives[0][0])
        self.assertIn("Ingreso Early editable para el correo.", mail.outbox[0].alternatives[0][0])
        self.assertIn("Tu QR queda adjunto en este correo", mail.outbox[0].alternatives[0][0])
        self.assertIn("cid:event_qr_inline", mail.outbox[0].alternatives[0][0])
        self.assertIn("cid:event_flyer_inline", mail.outbox[0].alternatives[0][0])
        self.assertIn('alt="Flyer del evento"', mail.outbox[0].alternatives[0][0])
        self.assertIn("width: 260px;", mail.outbox[0].alternatives[0][0])
        self.assertNotIn(f"QR: {self.attendee.qr_code}", mail.outbox[0].alternatives[0][0])
        self.assertEqual(mail.outbox[0].subject, "Acceso confirmado para Motaz en Evento Norte")
        self.assertEqual(mail.outbox[0].attachments, [])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attendee_ticket_email_omits_branch_reference(self):
        self.event.email_body = (
            "Tu registro para {event_name} fue confirmado.\n\n"
            "Sucursal: {branch_name}\n"
            "Fecha: {event_date}"
        )
        self.event.save()

        sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")
        self.assertNotIn("Sucursal:", mail.outbox[0].body)
        self.assertNotIn(self.branch.name, mail.outbox[0].body)
        self.assertNotIn("Sucursal:</strong>", mail.outbox[0].alternatives[0][0])
        self.assertNotIn(self.branch.name, mail.outbox[0].alternatives[0][0])

    def test_whatsapp_share_text_omits_branch_reference(self):
        self.event.email_body = (
            "Tu registro para {event_name} fue confirmado.\n\n"
            "Sucursal: {branch_name}\n"
            "Fecha: {event_date}"
        )
        self.event.save()

        share_text = build_event_share_text(self.event, self.attendee)

        self.assertNotIn("Sucursal:", share_text)
        self.assertNotIn(self.branch.name, share_text)

    def test_related_email_message_accepts_policy_argument(self):
        from ticketing.application import RelatedEmailMultiAlternatives

        message = RelatedEmailMultiAlternatives(
            subject="Prueba",
            body="Texto",
            from_email="test@example.com",
            to=["destino@example.com"],
        )
        message.attach_alternative("<p>HTML</p>", "text/html")

        built = message.message(policy=email.policy.SMTP)

        self.assertEqual(built["Subject"], "Prueba")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attendee_ticket_email_embeds_qr_as_png(self):
        sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")

        built = mail.outbox[0].message(policy=email.policy.SMTP)
        mime_dump = built.as_string()

        self.assertIn("Content-Type: image/png", mime_dump)
        self.assertNotIn("Content-Type: image/webp", mime_dump)
        self.assertIn("Content-ID: <event_qr_inline>", mime_dump)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attendee_ticket_email_embeds_flyer_inline_when_present(self):
        self.event.flyer = make_test_image("flyer-inline.png", color="#ff6600")
        self.event.save()

        sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")
        self.assertIn("cid:event_flyer_inline", mail.outbox[0].alternatives[0][0])

        built = mail.outbox[0].message(policy=email.policy.SMTP)
        mime_dump = built.as_string()
        self.assertIn("Content-ID: <event_flyer_inline>", mime_dump)

    def test_send_attendee_ticket_email_retries_without_smtp_auth(self):
        primary_connection = MagicMock()
        fallback_connection = MagicMock()
        with patch(
            "ticketing.application.get_connection",
            side_effect=[primary_connection, fallback_connection],
        ) as get_connection_mock, patch(
            "ticketing.application.RelatedEmailMultiAlternatives.send",
            side_effect=[
                smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server."),
                1,
            ],
        ) as send_mock:
            sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")
        self.assertEqual(get_connection_mock.call_count, 2)
        self.assertEqual(get_connection_mock.call_args_list[1].kwargs, {"username": "", "password": ""})
        self.assertEqual(send_mock.call_count, 2)

    def test_send_attendee_ticket_email_retries_once_on_network_error(self):
        primary_connection = MagicMock()
        retry_connection = MagicMock()
        with patch(
            "ticketing.application.get_connection",
            side_effect=[primary_connection, retry_connection],
        ), patch(
            "ticketing.application.RelatedEmailMultiAlternatives.send",
            side_effect=[OSError(101, "Network is unreachable"), 1],
        ) as send_mock:
            sent, error = send_attendee_ticket_email(self.attendee)

        self.assertTrue(sent)
        self.assertEqual(error, "Correo enviado.")
        self.assertEqual(send_mock.call_count, 2)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attendee_create_sends_email_with_qr_attachment(self):
        client = Client()
        self.assertTrue(client.login(username="operador", password="12345678"))
        session = client.session
        session["current_branch_id"] = self.branch.id
        session["current_event_id"] = self.event.id
        session.save()

        response = client.post(
            reverse("attendees:create"),
            {
                "name": "Invitado Mail",
                "cc": "456",
                "phone": "301",
                "email": "invitado@test.com",
                "category": self.category.id,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["invitado@test.com"])
        self.assertEqual(mail.outbox[0].subject, "Acceso confirmado para Invitado Mail en Evento Norte")
        self.assertEqual(mail.outbox[0].attachments, [])
        self.assertIn("Ingreso Early editable para el correo.", mail.outbox[0].alternatives[0][0])
        self.assertIn("Tu QR queda adjunto en este correo", mail.outbox[0].alternatives[0][0])
        self.assertIn("cid:event_qr_inline", mail.outbox[0].alternatives[0][0])
        self.assertContains(response, "Asistente Invitado Mail registrado correctamente.")
        self.assertNotContains(response, "Entrega de correo no confirmada")
        self.assertNotContains(response, "QR para copiar")
