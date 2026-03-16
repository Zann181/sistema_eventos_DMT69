from django.db import models
from django.utils.text import slugify


def get_principal_branch():
    return Branch.objects.order_by("created_at", "id").first()


class Branch(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    code_prefix = models.CharField(max_length=12, default="DMT")
    primary_color = models.CharField(max_length=7, default="#1d3557")
    secondary_color = models.CharField(max_length=7, default="#e63946")
    page_background_color = models.CharField(max_length=7, default="#f4f1ea")
    surface_color = models.CharField(max_length=7, default="#fffdf8")
    panel_color = models.CharField(max_length=7, default="#efe7dc")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    logo = models.ImageField(upload_to="branches/logos/", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

        from media_assets.application import persist_image_asset

        persist_image_asset(self, "logo", "branch_logo")

    def __str__(self):
        return self.name
