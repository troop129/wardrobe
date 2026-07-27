import importlib.util
import logging
from abc import ABC, abstractmethod
from io import BytesIO

import httpx
from PIL import Image, ImageFilter

from app.config import get_settings

logger = logging.getLogger(__name__)

# Soft fringe / ghosting below this alpha is crushed to fully transparent.
_ALPHA_FLOOR = 24
# Pixels above this are treated as solid foreground for component labeling.
_ALPHA_SOLID = 128
# Keep secondary blobs only when they are a meaningful fraction of the main subject
# (e.g. a shoe pair). Smaller floaters (hangers, hats, tags) get dropped.
_MIN_SECONDARY_AREA_RATIO = 0.12


class BackgroundRemovalProvider(ABC):
    @abstractmethod
    def remove(self, image: Image.Image) -> Image.Image:
        """Remove background from image. Returns RGBA image with transparent background."""


def refine_cutout(image: Image.Image) -> Image.Image:
    """Clean rembg output: crush soft ghosts and drop small disconnected junk.

    rembg often leaves hanger hooks, floating accessories, lace strings, and
    translucent "halos" under soles. We:
      1. Zero near-transparent fringe pixels
      2. Keep only the largest connected foreground component(s)
      3. Lightly feather the alpha edge so hard thresholds don't look jagged
    """
    rgba = image.convert("RGBA")

    try:
        import numpy as np
    except ImportError:
        return _refine_cutout_pillow(rgba)

    arr = np.array(rgba)
    alpha = arr[:, :, 3].astype(np.uint8)
    alpha = np.where(alpha < _ALPHA_FLOOR, 0, alpha)

    binary = (alpha >= _ALPHA_SOLID).astype(np.uint8) * 255
    keep_mask = _largest_component_mask(binary)

    if keep_mask is not None:
        alpha = np.where(keep_mask, alpha, 0)

    arr[:, :, 3] = alpha
    out = Image.fromarray(arr, "RGBA")
    return _feather_alpha(out)


def _largest_component_mask(binary: "object") -> "object | None":
    """Return a boolean mask of the main subject blob(s), or None if unavailable."""
    try:
        import cv2
    except ImportError:
        return _largest_component_mask_numpy(binary)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n_labels <= 1:
        return None

    areas = [(i, int(stats[i, cv2.CC_STAT_AREA])) for i in range(1, n_labels)]
    areas.sort(key=lambda item: item[1], reverse=True)
    largest_area = areas[0][1]
    if largest_area <= 0:
        return None

    keep = {areas[0][0]}
    for label, area in areas[1:]:
        if area >= largest_area * _MIN_SECONDARY_AREA_RATIO:
            keep.add(label)
        else:
            break

    import numpy as np

    return np.isin(labels, list(keep))


def _largest_component_mask_numpy(binary: "object") -> "object | None":
    """Connected-component keep-mask using only numpy (no OpenCV/SciPy)."""
    try:
        import numpy as np
    except ImportError:
        return None

    foreground = binary > 0
    h, w = foreground.shape
    visited = np.zeros((h, w), dtype=bool)
    components: list[tuple[int, list[tuple[int, int]]]] = []

    neighbors = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )

    for y in range(h):
        for x in range(w):
            if not foreground[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            pixels: list[tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                pixels.append((cy, cx))
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if (
                        0 <= ny < h
                        and 0 <= nx < w
                        and foreground[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            components.append((len(pixels), pixels))

    if not components:
        return None

    components.sort(key=lambda item: item[0], reverse=True)
    largest_area = components[0][0]
    if largest_area <= 0:
        return None

    keep_pixels = list(components[0][1])
    for area, pixels in components[1:]:
        if area >= largest_area * _MIN_SECONDARY_AREA_RATIO:
            keep_pixels.extend(pixels)
        else:
            break

    mask = np.zeros((h, w), dtype=bool)
    for y, x in keep_pixels:
        mask[y, x] = True
    return mask


def _feather_alpha(image: Image.Image) -> Image.Image:
    """Slight blur on the alpha channel only to soften jagged mask edges."""
    r, g, b, a = image.split()
    a = a.filter(ImageFilter.GaussianBlur(radius=0.6))
    return Image.merge("RGBA", (r, g, b, a))


def _refine_cutout_pillow(image: Image.Image) -> Image.Image:
    """Cleanup when numpy isn't available: crush soft fringe + drop small blobs."""
    width, height = image.size
    pixels = list(image.getdata())

    alpha_floor_cleared = [
        (r, g, b, 0 if a < _ALPHA_FLOOR else a) for (r, g, b, a) in pixels
    ]

    foreground = [a >= _ALPHA_SOLID for (_, _, _, a) in alpha_floor_cleared]
    visited = [False] * (width * height)
    components: list[tuple[int, list[int]]] = []
    neighbors = (
        -width - 1,
        -width,
        -width + 1,
        -1,
        1,
        width - 1,
        width,
        width + 1,
    )

    for i, is_fg in enumerate(foreground):
        if not is_fg or visited[i]:
            continue
        stack = [i]
        visited[i] = True
        members: list[int] = []
        while stack:
            idx = stack.pop()
            members.append(idx)
            cy, cx = divmod(idx, width)
            for delta in neighbors:
                nidx = idx + delta
                if nidx < 0 or nidx >= width * height:
                    continue
                ny, nx = divmod(nidx, width)
                if abs(ny - cy) > 1 or abs(nx - cx) > 1:
                    continue
                if foreground[nidx] and not visited[nidx]:
                    visited[nidx] = True
                    stack.append(nidx)
        components.append((len(members), members))

    if components:
        components.sort(key=lambda item: item[0], reverse=True)
        largest = components[0][0]
        keep = set(components[0][1])
        for area, members in components[1:]:
            if area >= largest * _MIN_SECONDARY_AREA_RATIO:
                keep.update(members)
            else:
                break
        cleaned = [
            (r, g, b, a if i in keep else 0)
            for i, (r, g, b, a) in enumerate(alpha_floor_cleared)
        ]
    else:
        cleaned = alpha_floor_cleared

    out = Image.new("RGBA", (width, height))
    out.putdata(cleaned)
    return _feather_alpha(out)


class RembgProvider(BackgroundRemovalProvider):
    def __init__(self, model: str = "isnet-general-use"):
        self.model = model
        self._session = None

    def _get_session(self):
        if self._session is None:
            from rembg import new_session

            self._session = new_session(self.model)
        return self._session

    def remove(self, image: Image.Image) -> Image.Image:
        from rembg import remove

        # post_process_mask runs rembg's morphological cleanup; refine_cutout
        # then drops small disconnected floaters rembg still leaves behind.
        result = remove(
            image,
            session=self._get_session(),
            post_process_mask=True,
        )
        return refine_cutout(result)


class HttpProvider(BackgroundRemovalProvider):
    def __init__(self, url: str, api_key: str | None = None):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def remove(self, image: Image.Image) -> Image.Image:
        buf = BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.post(
                f"{self.url}/api/remove-background",
                files={"file": ("image.png", buf, "image/png")},
                headers=headers,
            )
            response.raise_for_status()

        result = Image.open(BytesIO(response.content)).convert("RGBA")
        return refine_cutout(result)


_provider: BackgroundRemovalProvider | None = None


def get_provider() -> BackgroundRemovalProvider:
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    provider_type = settings.bg_removal_provider

    if provider_type == "rembg":
        _provider = RembgProvider(model=settings.bg_removal_model)
    elif provider_type == "http":
        if not settings.bg_removal_url:
            raise ValueError("BG_REMOVAL_URL is required when BG_REMOVAL_PROVIDER=http")
        _provider = HttpProvider(url=settings.bg_removal_url, api_key=settings.bg_removal_api_key)
    else:
        raise ValueError(f"Unknown BG_REMOVAL_PROVIDER: {provider_type}. Use 'rembg' or 'http'.")

    return _provider


def is_available() -> bool:
    """Best-effort check for whether a background-removal provider can actually work.

    Used to gate automatic (on-upload) and bulk background removal so they no-op
    quietly instead of queuing jobs that would just fail (e.g. rembg not installed,
    or BG_REMOVAL_PROVIDER=http with no reachable BG_REMOVAL_URL).

    Note: RembgProvider defers its `import rembg` until first use (loading the
    model session is expensive), so get_provider() alone always succeeds for the
    default "rembg" setting even when the optional rembg package isn't installed.
    Check module resolvability separately for that case, without importing it
    (avoids the download/session-load cost just to answer "is this available?").
    """
    try:
        provider = get_provider()
    except Exception:
        return False

    if isinstance(provider, RembgProvider):
        return importlib.util.find_spec("rembg") is not None
    return True
