import logging
from uuid import UUID

logger = logging.getLogger(__name__)

ITEM_ROLE: dict[str, str] = {
    "shirt": "base_top",
    "t-shirt": "base_top",
    "blouse": "base_top",
    "polo": "base_top",
    "tank-top": "base_top",
    "top": "base_top",
    "sweater": "base_top",
    "pants": "bottom",
    "jeans": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "dress": "full_body",
    "jumpsuit": "full_body",
    "cardigan": "mid_layer",
    "vest": "mid_layer",
    "jacket": "outer_layer",
    "blazer": "outer_layer",
    "coat": "outer_layer",
    "hoodie": "outer_layer",
    "shoes": "footwear",
    "sneakers": "footwear",
    "boots": "footwear",
    "sandals": "footwear",
    "socks": "socks",
    "tie": "neckwear",
    "hat": "accessory",
    "scarf": "accessory",
    "belt": "accessory",
    "bag": "accessory",
    "accessories": "accessory",
    "cologne": "accessory",
    # Non-canonical aliases (see TYPE_ALIASES below) kept here too as defense in
    # depth for body-slot dedup, in case a record still has the raw alias value
    # (e.g. written directly to the DB, bypassing ItemService normalization).
    "tee": "base_top",
    "fragrance": "accessory",
}

# Non-canonical type/color spellings seen in the wild (manual edits, imports from
# other tools, older tagging runs) that should collapse onto the vocabulary in
# clothing_analysis.txt / ai_service.VALID_TYPES so scoring, dedup, and preference
# matching (which all compare raw strings) treat them as the same value. Applied to
# free-text writes from the manual item-edit path — see ItemService.update() — since
# that path deliberately doesn't reject unknown values, only normalizes known aliases.
TYPE_ALIASES: dict[str, str] = {
    "tee": "t-shirt",
    "tshirt": "t-shirt",
    "fragrance": "cologne",
    "perfume": "cologne",
}

COLOR_ALIASES: dict[str, str] = {
    "grey": "gray",
    "light grey": "gray",
    "light gray": "gray",
    "dark grey": "gray",
    "dark gray": "gray",
    "charcoal": "gray",
    "beluga": "gray",
    "off-white": "cream",
    "ivory": "cream",
    "wine": "burgundy",
    "maroon": "burgundy",
    "forest green": "green",
    "dark blue": "navy",
    "royal blue": "blue",
    "sky blue": "light-blue",
    "baby blue": "light-blue",
    "camel": "tan",
    "khaki": "tan",
    "light brown": "tan",
    "dark brown": "brown",
    "rust": "orange",
    "coral": "pink",
    "rose": "pink",
    "mauve": "purple",
    "lavender": "purple",
    "mustard": "yellow",
}


def normalize_type(value: str | None) -> str | None:
    """Lowercase and alias-normalize a free-text item type. Unknown values pass
    through unchanged — this only collapses known synonyms, it never rejects."""
    if not value:
        return value
    cleaned = value.strip().lower()
    return TYPE_ALIASES.get(cleaned, cleaned)


def normalize_color(value: str | None) -> str | None:
    """Lowercase and alias-normalize a free-text color. Unknown values pass
    through unchanged — this only collapses known synonyms, it never rejects."""
    if not value:
        return value
    cleaned = value.strip().lower()
    return COLOR_ALIASES.get(cleaned, cleaned)


def deduplicate_by_body_slot(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[UUID]:
    seen_roles: dict[str, UUID] = {}
    result: list[UUID] = []
    has_full_body = any(
        ITEM_ROLE.get(item_type_map.get(iid, "")) == "full_body" for iid in item_ids
    )
    for iid in item_ids:
        item_type = item_type_map.get(iid, "")
        role = ITEM_ROLE.get(item_type)
        if not role:
            result.append(iid)
            continue
        if role == "accessory":
            result.append(iid)
            continue
        if has_full_body and role in ("base_top", "bottom"):
            logger.warning(f"Removing {item_type} item {iid}: full_body item present")
            continue
        if role in seen_roles:
            logger.warning(
                f"Removing duplicate {role} item {iid} ({item_type}): "
                f"role already filled by {seen_roles[role]}"
            )
            continue
        seen_roles[role] = iid
        result.append(iid)
    return result


_CANONICAL_ROLE_ORDER = [
    "full_body",
    "base_top",
    "mid_layer",
    "outer_layer",
    "bottom",
    "footwear",
    "socks",
    "neckwear",
    "accessory",
]

_ROLE_SORT_INDEX: dict[str, int] = {role: idx for idx, role in enumerate(_CANONICAL_ROLE_ORDER)}


def canonical_item_order(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[UUID]:
    original_positions = {iid: idx for idx, iid in enumerate(item_ids)}

    def sort_key(item_id: UUID) -> tuple[int, int]:
        item_type = item_type_map.get(item_id, "")
        role = ITEM_ROLE.get(item_type)
        role_idx = (
            _ROLE_SORT_INDEX.get(role, len(_CANONICAL_ROLE_ORDER))
            if role
            else len(_CANONICAL_ROLE_ORDER)
        )
        return (role_idx, original_positions[item_id])

    return sorted(item_ids, key=sort_key)
