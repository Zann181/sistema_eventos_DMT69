import hashlib
import os
from io import BytesIO

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from media_assets.models import MediaAsset


def _normalized_name(original_name, extension):
    base_name = os.path.splitext(os.path.basename(original_name))[0]
    return f"{base_name}.{extension.lower()}"


def _target_format_for_kind(kind):
    if kind in {"branch_logo", "event_logo", "event_qr_logo"}:
        return "PNG"
    return "WEBP"


def _normalize_image(field_file, *, target_format):
    field_file.open("rb")
    with Image.open(field_file) as opened_image:
        image = opened_image.copy()

    if target_format == "PNG":
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    output = BytesIO()
    save_kwargs = {"format": target_format}
    if target_format == "WEBP":
        save_kwargs.update({"quality": 88, "method": 6})
    elif target_format == "PNG":
        save_kwargs.update({"optimize": True})
    image.save(output, **save_kwargs)
    content = output.getvalue()
    return {
        "name": _normalized_name(field_file.name, target_format),
        "content": content,
        "checksum": hashlib.sha256(content).hexdigest(),
        "width": image.width,
        "height": image.height,
        "size_bytes": len(content),
    }


def field_file_exists(field_file):
    if not field_file or not getattr(field_file, "name", ""):
        return False
    return default_storage.exists(field_file.name)


def get_media_asset(instance, kind):
    if not getattr(instance, "pk", None):
        return None
    content_type = ContentType.objects.get_for_model(instance.__class__)
    return MediaAsset.objects.filter(content_type=content_type, object_id=instance.pk, kind=kind).first()


def restore_field_from_asset(instance, field_name, kind):
    asset = get_media_asset(instance, kind)
    if not asset or not asset.file:
        return None
    if not default_storage.exists(asset.file.name):
        return None

    current_field = getattr(instance, field_name, None)
    current_name = getattr(current_field, "name", "") if current_field else ""
    if current_name != asset.file.name:
        setattr(instance, field_name, asset.file.name)
        instance.__class__.objects.filter(pk=instance.pk).update(**{field_name: asset.file.name})
    return getattr(instance, field_name, None)


def resolve_field_file(instance, field_name, kind):
    field_file = getattr(instance, field_name, None)
    if field_file_exists(field_file):
        return field_file
    return restore_field_from_asset(instance, field_name, kind)


def persist_image_asset(instance, field_name, kind):
    field_file = getattr(instance, field_name, None)
    if not field_file or not field_file_exists(field_file):
        return

    target_format = _target_format_for_kind(kind)
    target_extension = target_format.lower()
    existing_asset = get_media_asset(instance, kind)
    if (
        existing_asset
        and getattr(existing_asset.file, "name", "") == field_file.name
        and field_file.name.lower().endswith(f".{target_extension}")
    ):
        return existing_asset

    normalized = _normalize_image(field_file, target_format=target_format)
    if not field_file.name.lower().endswith(f".{target_extension}"):
        field_file.save(normalized["name"], ContentFile(normalized["content"]), save=False)
        instance.__class__.objects.filter(pk=instance.pk).update(**{field_name: field_file.name})

    content_type = ContentType.objects.get_for_model(instance.__class__)
    MediaAsset.objects.update_or_create(
        content_type=content_type,
        object_id=instance.pk,
        kind=kind,
        defaults={
            "file": field_file.name,
            "checksum": normalized["checksum"],
            "width": normalized["width"],
            "height": normalized["height"],
            "size_bytes": normalized["size_bytes"],
        },
    )
