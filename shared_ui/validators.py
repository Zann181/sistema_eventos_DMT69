from django.core.exceptions import ValidationError


def validate_png_upload(upload, *, field_label="archivo"):
    if not upload:
        return upload

    content_type = (getattr(upload, "content_type", "") or "").lower()
    filename = (getattr(upload, "name", "") or "").lower()
    valid_content_types = {"image/png", "image/x-png"}
    if content_type not in valid_content_types and not filename.endswith(".png"):
        raise ValidationError(f"El campo {field_label} solo acepta imagenes PNG.")
    return upload


def validate_image_upload(upload, *, field_label="archivo"):
    if not upload:
        return upload

    content_type = (getattr(upload, "content_type", "") or "").lower()
    filename = (getattr(upload, "name", "") or "").lower()
    if content_type.startswith("image/"):
        return upload

    valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    if filename.endswith(valid_extensions):
        return upload

    raise ValidationError(f"El campo {field_label} solo acepta archivos de imagen.")
