"""Human-readable item names that preserve brand/product casing.

Vision and the item assistant often return proper names ("Dior Sauvage", "YSL").
Blind ``str.title()`` mangles those; this module builds fallbacks without
overwriting a good name the model or user already provided.
"""

from __future__ import annotations

# Types where product/brand identity matters more than color+fit+garment.
_PRODUCT_LED_TYPES = frozenset({"cologne"})

# Known brand/acronym spellings when we only have a lowercased slug.
_BRAND_CASING: dict[str, str] = {
    "h&m": "H&M",
    "hm": "H&M",
    "ysl": "YSL",
    "lv": "LV",
    "nike": "Nike",
    "adidas": "Adidas",
    "zara": "Zara",
    "uniqlo": "Uniqlo",
    "gucci": "Gucci",
    "dior": "Dior",
    "chanel": "Chanel",
    "prada": "Prada",
    "yeezy": "Yeezy",
}

_TYPE_DISPLAY: dict[str, str] = {
    "t-shirt": "T-Shirt",
    "tank-top": "Tank Top",
    "light-blue": "Light Blue",
}


def format_vocab_token(value: str) -> str:
    """Display a controlled-vocab slug (color/type/fit) without mangling brands."""
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    key = cleaned.lower()
    if key in _TYPE_DISPLAY:
        return _TYPE_DISPLAY[key]
    if key in _BRAND_CASING:
        return _BRAND_CASING[key]
    # Hyphenated slugs → Title Case words; leave mixed/ALLCAPS tokens alone.
    if "-" in cleaned:
        return " ".join(part.capitalize() for part in cleaned.split("-"))
    if cleaned.isupper() or not cleaned.islower():
        return cleaned
    return cleaned.capitalize()


def format_brand(brand: str) -> str:
    """Preserve brand casing; only normalize when the value is fully lowercased."""
    cleaned = brand.strip()
    if not cleaned:
        return cleaned
    key = cleaned.lower()
    if key in _BRAND_CASING:
        return _BRAND_CASING[key]
    if cleaned.isupper() or any(c.isupper() for c in cleaned[1:]):
        return cleaned
    # "dior sauvage" → "Dior Sauvage"; "mcqueen" stays capitalize-only (no magic).
    return " ".join(format_vocab_token(part) for part in cleaned.split())


def is_vague_name(name: str | None, item_type: str | None = None) -> bool:
    """True when a name is empty or just restates the type."""
    if not name or not name.strip():
        return True
    cleaned = name.strip().lower()
    if item_type and cleaned in {item_type.lower(), item_type.lower().replace("-", " ")}:
        return True
    if cleaned in {"item", "clothing", "unknown", "untitled"}:
        return True
    return False


def descriptive_item_name(
    *,
    brand: str | None = None,
    primary_color: str | None = None,
    fit: str | None = None,
    item_type: str | None = None,
    subtype: str | None = None,
) -> str | None:
    """Build a readable fallback name from structured fields.

    Fragrance/product-led types prefer brand + product (subtype) over color/fit.
    Returns None when there isn't enough signal for a useful label.
    """
    type_key = (item_type or "").strip().lower() or None
    brand_part = format_brand(brand) if brand and brand.strip() else None
    subtype_part = subtype.strip() if subtype and subtype.strip() else None
    color_part = format_vocab_token(primary_color) if primary_color and primary_color.strip() else None
    fit_part = format_vocab_token(fit) if fit and fit.strip() else None
    type_part = (
        format_vocab_token(item_type)
        if item_type and item_type.strip() and type_key != "unknown"
        else None
    )

    if type_key in _PRODUCT_LED_TYPES:
        parts = [p for p in (brand_part, subtype_part, type_part) if p]
        # Avoid "Dior Eau De Parfum Cologne" noise when subtype alone is enough with brand.
        if brand_part and subtype_part:
            parts = [brand_part, subtype_part]
        elif brand_part and type_part:
            parts = [brand_part, type_part]
        elif subtype_part and type_part:
            parts = [subtype_part]
        if len(parts) >= 1 and (brand_part or subtype_part):
            return " ".join(parts)[:100]
        return None

    # Footwear / accessories: brand + color + subtype-or-type (skip garment fit).
    if type_key in {
        "shoes",
        "sneakers",
        "boots",
        "sandals",
        "hat",
        "scarf",
        "belt",
        "bag",
        "accessories",
        "tie",
        "socks",
    }:
        if subtype_part and "-" in subtype_part:
            garment = "-".join(p.capitalize() for p in subtype_part.split("-"))
        elif subtype_part:
            garment = format_vocab_token(subtype_part)
        else:
            garment = type_part
        parts = [p for p in (brand_part, color_part, garment) if p]
        if len(parts) < 2:
            return None
        return " ".join(parts)[:100]

    # Apparel: brand + color + fit + type
    parts = [p for p in (brand_part, color_part, fit_part, type_part) if p]
    if len(parts) < 2:
        return None
    return " ".join(parts)[:100]


def resolve_item_name(
    *,
    preferred: str | None = None,
    existing: str | None = None,
    brand: str | None = None,
    primary_color: str | None = None,
    fit: str | None = None,
    item_type: str | None = None,
    subtype: str | None = None,
) -> str | None:
    """Pick the best display name without clobbering a good preferred/existing one."""
    if preferred and not is_vague_name(preferred, item_type):
        return preferred.strip()[:100]
    if existing and not is_vague_name(existing, item_type):
        return existing.strip()[:100]
    return descriptive_item_name(
        brand=brand,
        primary_color=primary_color,
        fit=fit,
        item_type=item_type,
        subtype=subtype,
    )
