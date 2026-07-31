from datetime import UTC, datetime
from uuid import uuid4

from app.models.item import ClothingItem
from app.services.item_scorer import ScoredItem
from app.services.rule_composer import compose_rule_outfits
from app.services.weather_service import WeatherData


def _weather(temp: float) -> WeatherData:
    return WeatherData(
        temperature=temp,
        feels_like=temp,
        humidity=50,
        precipitation_chance=0,
        precipitation_mm=0,
        wind_speed=0,
        condition="sunny",
        condition_code=0,
        is_day=True,
        uv_index=1,
        timestamp=datetime.now(UTC),
    )


def _item(item_type: str, color: str, score: float = 1.0, **tags) -> ScoredItem:
    item = ClothingItem(
        id=uuid4(),
        user_id=uuid4(),
        type=item_type,
        image_path="test.jpg",
        primary_color=color,
        colors=[color],
        tags=tags,
        style=[],
        season=[],
    )
    return ScoredItem(item=item, score=score)


def test_rules_build_complete_diverse_outfits_without_ai():
    items = [
        _item("shirt", "white", 1.0),
        _item("t-shirt", "black", 0.9),
        _item("pants", "navy", 1.0),
        _item("jeans", "blue", 0.9),
        _item("shoes", "brown", 1.0),
        _item("sneakers", "white", 0.9),
    ]

    outfits = compose_rule_outfits(
        items,
        good_pairs={},
        weather=_weather(27),
        preferences=None,
        occasion="casual",
    )

    assert len(outfits) == 3
    assert all(len(outfit.item_ids) == 3 for outfit in outfits)
    assert len({tuple(outfit.item_ids[:2]) for outfit in outfits}) > 1


def test_known_pair_beats_slightly_higher_individual_scores():
    white_shirt = _item("shirt", "white", 0.9)
    black_shirt = _item("shirt", "black", 1.0)
    blue_pants = _item("pants", "blue", 0.9)
    black_pants = _item("pants", "black", 1.0)
    shoes = _item("shoes", "brown", 1.0)
    good_pairs = {
        white_shirt.item.id: [blue_pants.item.id],
        blue_pants.item.id: [white_shirt.item.id],
    }

    outfit = compose_rule_outfits(
        [white_shirt, black_shirt, blue_pants, black_pants, shoes],
        good_pairs=good_pairs,
        weather=_weather(24),
        preferences=None,
        occasion="casual",
        limit=1,
    )[0]

    assert white_shirt.item.id in outfit.item_ids
    assert blue_pants.item.id in outfit.item_ids
    assert "Keeps 1 combination" in outfit.highlights[0]


def test_layers_in_cool_weather_and_skips_them_in_heat():
    core = [
        _item("shirt", "white"),
        _item("pants", "navy"),
        _item("shoes", "brown"),
    ]
    jacket = _item("jacket", "blue")

    cool = compose_rule_outfits(
        [*core, jacket],
        good_pairs={},
        weather=_weather(14),
        preferences=None,
        occasion="casual",
        limit=1,
    )[0]
    hot = compose_rule_outfits(
        [*core, jacket],
        good_pairs={},
        weather=_weather(29),
        preferences=None,
        occasion="casual",
        limit=1,
    )[0]

    assert jacket.item.id in cool.item_ids
    assert cool.layers
    assert jacket.item.id not in hot.item_ids
    assert not hot.layers


def test_fragrance_is_selected_for_date_by_family_and_temperature():
    core = [
        _item("shirt", "white"),
        _item("pants", "navy"),
        _item("shoes", "brown"),
    ]
    fresh = _item("cologne", "blue", fragrance_family="fresh")
    woody = _item("cologne", "brown", fragrance_family="woody")

    outfit = compose_rule_outfits(
        [*core, fresh, woody],
        good_pairs={},
        weather=_weather(28),
        preferences=None,
        occasion="date",
        limit=1,
    )[0]

    assert fresh.item.id in outfit.item_ids
    assert woody.item.id not in outfit.item_ids
