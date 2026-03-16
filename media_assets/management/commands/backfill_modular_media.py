from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from attendees.models import Attendee
from branches.models import Branch
from catalog.models import Product
from events.models import Event
from media_assets.application import field_file_exists, persist_image_asset
from ticketing.application import generate_attendee_qr


def build_placeholder_image():
    image = Image.new("RGB", (480, 480), "#102542")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 440, 440), radius=36, outline="#f8f9fa", width=8)
    draw.text((110, 215), "DMT", fill="#f8f9fa")
    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=88, method=6)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Normaliza media legado a WebP y crea metadata para la arquitectura modular."

    def handle(self, *args, **options):
        placeholder = build_placeholder_image()

        for branch in Branch.objects.all():
            if branch.logo and field_file_exists(branch.logo):
                persist_image_asset(branch, "logo", "branch_logo")

        for event in Event.objects.all():
            if event.logo and field_file_exists(event.logo):
                persist_image_asset(event, "logo", "event_logo")
            if event.flyer and field_file_exists(event.flyer):
                persist_image_asset(event, "flyer", "event_flyer")

        for product in Product.objects.all():
            if not product.image or not field_file_exists(product.image):
                product.image.save(
                    f"product-{product.pk}.webp",
                    ContentFile(placeholder),
                    save=False,
                )
                product.save(update_fields=["image"])
            persist_image_asset(product, "image", "product_image")

        for attendee in Attendee.objects.all():
            if not attendee.qr_image or not field_file_exists(attendee.qr_image):
                generate_attendee_qr(attendee)
            else:
                persist_image_asset(attendee, "qr_image", "attendee_qr")

        self.stdout.write(self.style.SUCCESS("Backfill de media completado."))
