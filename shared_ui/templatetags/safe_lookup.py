from collections.abc import Mapping

from django import template


register = template.Library()


@register.filter
def dig(value, path):
    if value is None or not path:
        return None

    current = value
    for bit in str(path).split("."):
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = current.get(bit)
            continue
        if isinstance(current, (list, tuple)):
            try:
                current = current[int(bit)]
            except (TypeError, ValueError, IndexError):
                return None
            continue
        current = getattr(current, bit, None)
    return current
