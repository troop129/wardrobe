"""Deterministic outfit composition from ranked wardrobe items.

The LLM is useful for prose and fuzzy requests, but outfit structure and known
preferences are ordinary data problems.  This module composes complete outfits
from the scorer output, explicit/learned pairs, color harmony, weather, and the
user's layering preference without making a network call.
"""

from dataclasses import dataclass
from itertools import combinations, product
from uuid import UUID

from app.models.preference import UserPreference
from app.services.item_scorer import ScoredItem
from app.services.weather_service import WeatherData
from app.utils.clothing import ITEM_ROLE, canonical_item_order

NEUTRALS = {
    "black",
    "white",
    "gray",
    "navy",
    "beige",
    "brown",
    "cream",
    "tan",
    "khaki",
}
COLOR_FAMILIES = [
    {"blue", "light-blue", "navy", "teal"},
    {"green", "olive", "teal"},
    {"red", "burgundy", "pink", "orange"},
    {"brown", "tan", "beige", "cream", "orange"},
    {"purple", "pink", "burgundy"},
    {"black", "gray", "white"},
]
BOLD_PATTERNS = {"graphic", "plaid", "checkered", "floral", "geometric", "animal-print"}
FRAGRANCE_FREE_OCCASIONS = {"gym", "running", "hiking", "sport", "sporty"}


@dataclass(frozen=True)
class RuleOutfit:
    item_ids: list[UUID]
    headline: str
    highlights: list[str]
    styling_tip: str
    layers: dict[str, str]
    score: float


def _role(item: ScoredItem) -> str | None:
    return ITEM_ROLE.get((item.item.type or "").lower())


def _color(item: ScoredItem) -> str:
    return (item.item.primary_color or "").lower()


def _colors_harmonize(left: str, right: str) -> bool:
    if not left or not right or left == right or left in NEUTRALS or right in NEUTRALS:
        return True
    return any(left in family and right in family for family in COLOR_FAMILIES)


def _combination_quality(items: list[ScoredItem], good_pairs: dict[UUID, list[UUID]]) -> float:
    score = sum(item.score for item in items)
    colors = [_color(item) for item in items if _color(item)]
    patterns = [(item.item.pattern or "").lower() for item in items]

    for left, right in combinations(items, 2):
        if right.item.id in good_pairs.get(left.item.id, []):
            # A known good pair should outweigh small recency/season differences.
            score += 1.25
        if _colors_harmonize(_color(left), _color(right)):
            score += 0.12
        else:
            score -= 0.3
        if set(left.item.style or []) & set(right.item.style or []):
            score += 0.06

    if len({color for color in colors if color not in NEUTRALS}) > 2:
        score -= 0.4
    if sum(pattern in BOLD_PATTERNS for pattern in patterns) > 1:
        score -= 0.75
    return score


def _layer_limits(weather: WeatherData, preferences: UserPreference | None) -> tuple[int, str]:
    feels_like = weather.feels_like
    preference = preferences.layering_preference if preferences else "moderate"
    rain = weather.precipitation_chance >= 55

    if feels_like >= 25 and not rain:
        return 0, "It is warm enough to skip a layer."
    if feels_like <= 9:
        return 2, "Cold weather calls for a removable mid layer and outer layer."
    threshold = {"minimal": 13, "moderate": 20, "heavy": 23}.get(preference, 20)
    if feels_like <= threshold or rain:
        return 1, "A removable layer matches the temperature and weather."
    return 0, "The base outfit suits the current temperature without extra bulk."


def _best_addition(
    candidates: list[ScoredItem],
    current: list[ScoredItem],
    good_pairs: dict[UUID, list[UUID]],
    mandatory_ids: set[UUID],
) -> ScoredItem | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.item.id not in mandatory_ids,
            -_combination_quality([*current, item], good_pairs),
        ),
    )
    return ranked[0]


def _fragrance_score(item: ScoredItem, occasion: str, weather: WeatherData) -> float:
    tags = item.item.tags or {}
    score = item.score
    occasions = [str(value).lower() for value in tags.get("occasion", [])]
    family = str(tags.get("fragrance_family") or "").lower()
    if occasion in occasions:
        score += 0.7
    if weather.feels_like >= 24 and family in {"citrus", "fresh", "aquatic", "green"}:
        score += 0.35
    if weather.feels_like <= 14 and family in {"woody", "amber", "spicy", "gourmand", "leather"}:
        score += 0.35
    return score


def compose_rule_outfits(
    scored: list[ScoredItem],
    *,
    good_pairs: dict[UUID, list[UUID]],
    weather: WeatherData,
    preferences: UserPreference | None,
    occasion: str,
    mandatory_item_ids: set[UUID] | None = None,
    rejected_combinations: set[frozenset[UUID]] | None = None,
    worn_combinations: set[frozenset[UUID]] | None = None,
    limit: int = 3,
) -> list[RuleOutfit]:
    mandatory_ids = mandatory_item_ids or set()
    rejected = rejected_combinations or set()
    worn = worn_combinations or set()
    by_role: dict[str, list[ScoredItem]] = {}
    extras: list[ScoredItem] = []
    for item in scored:
        role = _role(item)
        if role:
            by_role.setdefault(role, []).append(item)
        else:
            extras.append(item)

    tops = by_role.get("base_top", [])[:10]
    bottoms = by_role.get("bottom", [])[:10]
    full_body = by_role.get("full_body", [])[:8]
    footwear = by_role.get("footwear", [])[:10]
    core_options: list[list[ScoredItem]] = []
    core_options.extend([list(parts) for parts in product(tops, bottoms, footwear)])
    core_options.extend([list(parts) for parts in product(full_body, footwear)])

    mandatory_core = {
        item_id
        for item_id in mandatory_ids
        if any(
            candidate.item.id == item_id
            for role in (tops, bottoms, full_body, footwear)
            for candidate in role
        )
    }
    ranked_cores: list[tuple[float, list[ScoredItem]]] = []
    for core in core_options:
        ids = {item.item.id for item in core}
        if not mandatory_core.issubset(ids):
            continue
        quality = _combination_quality(core, good_pairs)
        if frozenset(ids) in worn:
            quality -= 0.45
        ranked_cores.append((quality, core))
    ranked_cores.sort(key=lambda entry: entry[0], reverse=True)

    layer_count, layer_reason = _layer_limits(weather, preferences)
    mid_layers = by_role.get("mid_layer", [])
    outer_layers = by_role.get("outer_layer", [])
    colognes = [item for item in by_role.get("accessory", []) if item.item.type == "cologne"]
    other_extras = [
        item for item in [*by_role.get("accessory", []), *extras] if item.item.type != "cologne"
    ]

    candidates: list[RuleOutfit] = []
    for core_score, core in ranked_cores[:160]:
        selected = list(core)
        layers: dict[str, str] = {}

        mandatory_mid = [item for item in mid_layers if item.item.id in mandatory_ids]
        mandatory_outer = [item for item in outer_layers if item.item.id in mandatory_ids]
        desired_layers = max(layer_count, int(bool(mandatory_mid)) + int(bool(mandatory_outer)))
        for layer_name, required in (
            ("mid", mandatory_mid),
            ("outer", mandatory_outer),
        ):
            if required:
                layer = _best_addition(required, selected, good_pairs, mandatory_ids)
                if layer:
                    selected.append(layer)
                    layers[layer_name] = str(layer.item.id)

        remaining_layers = desired_layers - len(layers)
        for layer_name, pool in (("outer", outer_layers), ("mid", mid_layers)):
            if remaining_layers <= 0 or layer_name in layers:
                continue
            layer = _best_addition(pool, selected, good_pairs, mandatory_ids)
            if layer and layer.item.id not in {item.item.id for item in selected}:
                selected.append(layer)
                layers[layer_name] = str(layer.item.id)
                remaining_layers -= 1

        mandatory_cologne = [item for item in colognes if item.item.id in mandatory_ids]
        paired_cologne = [
            fragrance
            for fragrance in colognes
            if any(core_item.item.id in good_pairs.get(fragrance.item.id, []) for core_item in core)
        ]
        occasion_cologne = [
            fragrance
            for fragrance in colognes
            if occasion
            in [str(value).lower() for value in (fragrance.item.tags or {}).get("occasion", [])]
        ]
        add_fragrance = occasion not in FRAGRANCE_FREE_OCCASIONS and (
            bool(mandatory_cologne)
            or bool(paired_cologne)
            or bool(occasion_cologne)
            or occasion in {"date", "party", "formal", "dinner", "wedding"}
        )
        if add_fragrance and colognes:
            fragrance = max(
                mandatory_cologne or paired_cologne or occasion_cologne or colognes,
                key=lambda item: _fragrance_score(item, occasion, weather),
            )
            selected.append(fragrance)

        for extra in other_extras:
            if extra.item.id in mandatory_ids and extra.item.id not in {
                i.item.id for i in selected
            }:
                selected.append(extra)

        ids = [item.item.id for item in selected]
        if not mandatory_ids.issubset(ids):
            continue
        exact = frozenset(ids)
        if exact in rejected:
            continue

        type_map = {item.item.id: item.item.type for item in selected}
        ordered_ids = canonical_item_order(ids, type_map)
        selected_by_id = {item.item.id: item for item in selected}
        selected = [selected_by_id[item_id] for item_id in ordered_ids]
        pair_count = sum(
            right.item.id in good_pairs.get(left.item.id, [])
            for left, right in combinations(selected, 2)
        )
        core_colors = [_color(item) for item in core if _color(item)]
        color_label = " + ".join(dict.fromkeys(core_colors[:2])) or "Balanced"
        highlights = [
            f"{color_label.title()} pieces follow deterministic color-harmony rules.",
            layer_reason,
        ]
        if pair_count:
            highlights.insert(
                0, f"Keeps {pair_count} combination(s) you have rated as working together."
            )
        if any(item.item.type == "cologne" for item in selected):
            highlights.append("The fragrance is matched to the occasion and temperature.")

        candidates.append(
            RuleOutfit(
                item_ids=[item.item.id for item in selected],
                headline=f"{color_label.title()} {occasion.title()}",
                highlights=highlights,
                styling_tip=(
                    "Use the layer open so the base colors stay visible."
                    if layers
                    else "Keep the silhouette clean and let the color pairing do the work."
                ),
                layers=layers,
                score=_combination_quality(selected, good_pairs) + core_score,
            )
        )

    candidates.sort(key=lambda option: option.score, reverse=True)
    chosen: list[RuleOutfit] = []
    seen_core_signatures: set[tuple[UUID, ...]] = set()
    for option in candidates:
        signature = tuple(
            item_id
            for item_id in option.item_ids
            if ITEM_ROLE.get(
                next((s.item.type or "").lower() for s in scored if s.item.id == item_id)
            )
            in {"base_top", "bottom", "full_body"}
        )
        if signature in seen_core_signatures:
            continue
        seen_core_signatures.add(signature)
        chosen.append(option)
        if len(chosen) >= limit:
            break

    if len(chosen) < limit:
        for option in candidates:
            if option not in chosen:
                chosen.append(option)
            if len(chosen) >= limit:
                break
    return chosen
