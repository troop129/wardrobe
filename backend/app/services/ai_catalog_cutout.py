"""Opt-in AI catalog cutouts via OpenAI Image API images.edit + local chroma key.

Pipeline:
  1. Prefer the `_orig` backup photo when present (true source, not a rembg cutout)
  2. images.edit with gpt-image-2 to remake a smooth product-style garment on chroma
  3. Soft-matte + despill the chroma into a transparent RGBA PNG

rembg stays the free auto/bulk default; this is a paid per-item action.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from app.config import get_settings

logger = logging.getLogger(__name__)

GREEN_KEY = (0, 255, 0)
MAGENTA_KEY = (255, 0, 255)

# Soft matte: distances (0–255 RGB space) for full transparent / full opaque.
_KEY_DIST_TRANSPARENT = 28
_KEY_DIST_OPAQUE = 95
# Despill: how aggressively to crush the key channel near fringes.
_DESPILL_STRENGTH = 0.65


class AICatalogCutoutError(Exception):
    """User-facing failure from the Image API or local matte step."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code


def is_available() -> bool:
    return get_settings().ai_catalog_cutout_enabled


def pick_chroma_key(source: Image.Image) -> tuple[int, int, int]:
    """Prefer green chroma unless the garment itself is green-dominant."""
    rgb = source.convert("RGB")
    # Sample a center crop so hanger/background don't dominate the decision.
    w, h = rgb.size
    crop = rgb.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    stats = ImageStat.Stat(crop)
    r, g, b = stats.mean
    if g > r + 25 and g > b + 25 and g > 90:
        return MAGENTA_KEY
    return GREEN_KEY


def build_catalog_prompt(chroma_rgb: tuple[int, int, int]) -> str:
    hex_color = f"#{chroma_rgb[0]:02X}{chroma_rgb[1]:02X}{chroma_rgb[2]:02X}"
    return (
        "Edit this clothing photo into a clean e-commerce catalog product shot of "
        "the same empty garment only. Center the garment with generous padding. "
        f"Place it on a perfectly uniform solid {hex_color} chroma background "
        "(no gradients, no floor, no studio paper texture). "
        "Remove only the person, mannequin, hanger, background clutter, cast shadows, "
        "reflections, and unrelated props. Preserve the exact color, proportions, "
        "silhouette, material texture, logos, prints, seams, stitching, panels, "
        "buttons, zippers, hardware, and construction from the reference photo. "
        "Standardize the catalog angle instead of preserving the source camera angle: "
        "show garments front-on, upright, and centered; show footwear as a clean lateral "
        "side profile with the toe pointing to the left; show bags and accessories straight-on. "
        "Use that same view consistently across items in the same product class. "
        "For fabric items, make the presentation look freshly steamed or ironed by "
        "removing only incidental temporary creases; never airbrush, smooth away, or "
        "alter weave, ribbing, knit texture, grain, embossing, or construction details. "
        "For footwear, keep the real toe shape, sole thickness and tread, laces, "
        "eyelets, tongue, overlays, and all visible branding. Keep natural structural "
        "folds; do not flatten, simplify, beautify away, or invent product details. "
        "Do not invent a different garment. "
        "No text, watermarks, or borders."
    )


def chroma_key_to_rgba(
    image: Image.Image,
    key_rgb: tuple[int, int, int] = GREEN_KEY,
    *,
    soft_matte: bool = True,
    despill: bool = True,
) -> Image.Image:
    """Key out a solid chroma background into an RGBA cutout with soft edges."""
    rgb = image.convert("RGB")
    try:
        import numpy as np
    except ImportError:
        return _chroma_key_pillow(rgb, key_rgb)

    arr = np.asarray(rgb, dtype=np.float32)
    key = np.array(key_rgb, dtype=np.float32)
    dist = np.sqrt(np.sum((arr - key) ** 2, axis=2))

    if soft_matte:
        alpha = (dist - _KEY_DIST_TRANSPARENT) / max(_KEY_DIST_OPAQUE - _KEY_DIST_TRANSPARENT, 1)
        alpha = np.clip(alpha, 0.0, 1.0)
    else:
        alpha = (dist >= _KEY_DIST_OPAQUE).astype(np.float32)

    out = arr.copy()
    if despill:
        # Crush the key channel toward the other two near transparent fringes.
        fringe = (alpha > 0.05) & (alpha < 0.95)
        if key_rgb == GREEN_KEY:
            other = np.maximum(out[:, :, 0], out[:, :, 2])
            spill = np.maximum(out[:, :, 1] - other, 0.0)
            out[:, :, 1] = np.where(fringe, out[:, :, 1] - spill * _DESPILL_STRENGTH, out[:, :, 1])
        elif key_rgb == MAGENTA_KEY:
            # Magenta = high R+B, low G — pull R/B toward G on fringes.
            spill_r = np.maximum(out[:, :, 0] - out[:, :, 1], 0.0)
            spill_b = np.maximum(out[:, :, 2] - out[:, :, 1], 0.0)
            out[:, :, 0] = np.where(
                fringe, out[:, :, 0] - spill_r * _DESPILL_STRENGTH, out[:, :, 0]
            )
            out[:, :, 2] = np.where(
                fringe, out[:, :, 2] - spill_b * _DESPILL_STRENGTH, out[:, :, 2]
            )

    rgba = np.dstack(
        [
            np.clip(out[:, :, 0], 0, 255).astype(np.uint8),
            np.clip(out[:, :, 1], 0, 255).astype(np.uint8),
            np.clip(out[:, :, 2], 0, 255).astype(np.uint8),
            (alpha * 255.0).astype(np.uint8),
        ]
    )
    result = Image.fromarray(rgba, "RGBA")
    # Feather only the soft matte. A caller requesting a hard matte expects
    # fully opaque product pixels to remain fully opaque.
    if not soft_matte:
        return result

    # Light feather so soft edges don't look jagged on thumbnails.
    r, g, b, a = result.split()
    a = a.filter(ImageFilter.GaussianBlur(radius=0.5))
    return Image.merge("RGBA", (r, g, b, a))


def _chroma_key_pillow(image: Image.Image, key_rgb: tuple[int, int, int]) -> Image.Image:
    """Fallback matte without numpy."""
    pixels = list(image.getdata())
    keyed: list[tuple[int, int, int, int]] = []
    kr, kg, kb = key_rgb
    span = max(_KEY_DIST_OPAQUE - _KEY_DIST_TRANSPARENT, 1)
    for r, g, b in pixels:
        dist = ((r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2) ** 0.5
        if dist <= _KEY_DIST_TRANSPARENT:
            alpha = 0
        elif dist >= _KEY_DIST_OPAQUE:
            alpha = 255
        else:
            alpha = int(255 * (dist - _KEY_DIST_TRANSPARENT) / span)
        keyed.append((r, g, b, alpha))
    out = Image.new("RGBA", image.size)
    out.putdata(keyed)
    return out


def edit_to_chroma_catalog(source_path: Path) -> Image.Image:
    """Call OpenAI images.edit and return the chroma catalog RGB image."""
    settings = get_settings()
    api_key = settings.effective_ai_image_api_key
    if not api_key:
        raise AICatalogCutoutError(
            "AI catalog cutout is not configured (set AI_IMAGE_API_KEY or AI_API_KEY).",
            code="not_configured",
        )

    source = Image.open(source_path).convert("RGB")
    key_rgb = pick_chroma_key(source)
    prompt = build_catalog_prompt(key_rgb)

    try:
        from openai import (
            APIError,
            AuthenticationError,
            BadRequestError,
            OpenAI,
            PermissionDeniedError,
        )
    except ImportError as e:
        raise AICatalogCutoutError(
            "openai package is not installed. Add openai to backend requirements.",
            code="missing_dependency",
        ) from e

    client = OpenAI(
        api_key=api_key,
        base_url=settings.ai_image_base_url.rstrip("/"),
        timeout=settings.ai_image_timeout,
    )

    try:
        with open(source_path, "rb") as image_file:
            result = client.images.edit(
                model=settings.ai_image_model,
                image=[image_file],
                prompt=prompt,
                size=settings.ai_image_size,  # type: ignore[arg-type]
                quality=settings.ai_image_quality,  # type: ignore[arg-type]
                output_format="png",
            )
    except AuthenticationError as e:
        raise AICatalogCutoutError(
            "OpenAI authentication failed for Image API. Check AI_IMAGE_API_KEY / AI_API_KEY.",
            code="auth_error",
        ) from e
    except PermissionDeniedError as e:
        raise AICatalogCutoutError(
            "OpenAI denied Image API access. Org may need GPT Image / Organization Verification.",
            code="permission_denied",
        ) from e
    except BadRequestError as e:
        message = str(e)
        code = "bad_request"
        lowered = message.lower()
        if "moderation" in lowered or "safety" in lowered:
            code = "moderation"
        elif "image_generation_user_error" in lowered:
            code = "image_generation_user_error"
        raise AICatalogCutoutError(
            f"Image edit rejected: {message}",
            code=code,
        ) from e
    except APIError as e:
        raise AICatalogCutoutError(
            f"OpenAI Image API error: {e}",
            code="api_error",
        ) from e
    except Exception as e:
        raise AICatalogCutoutError(
            f"AI catalog cutout failed: {e}",
            code="unknown",
        ) from e

    if not result.data or not result.data[0].b64_json:
        raise AICatalogCutoutError(
            "Image API returned no image data.",
            code="empty_response",
        )

    raw = base64.b64decode(result.data[0].b64_json)
    chroma = Image.open(BytesIO(raw)).convert("RGB")
    # Stash the key used so callers can matte with the same color.
    chroma.info["chroma_key"] = key_rgb
    return chroma


def generate_transparent_cutout(source_path: Path) -> Image.Image:
    """Full pipeline: images.edit → chroma key → RGBA."""
    chroma = edit_to_chroma_catalog(source_path)
    key_rgb = chroma.info.get("chroma_key") or pick_chroma_key(chroma)
    # Prefer keying with the prompt color; also try detecting dominant corner color
    # in case the model drifted slightly.
    corners = [
        chroma.getpixel((2, 2)),
        chroma.getpixel((chroma.width - 3, 2)),
        chroma.getpixel((2, chroma.height - 3)),
        chroma.getpixel((chroma.width - 3, chroma.height - 3)),
    ]
    # If corners look more like magenta than green, switch.
    avg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    if avg[0] > 180 and avg[2] > 180 and avg[1] < 80:
        key_rgb = MAGENTA_KEY
    elif avg[1] > 180 and avg[0] < 80 and avg[2] < 80:
        key_rgb = GREEN_KEY

    return chroma_key_to_rgba(chroma, key_rgb)
