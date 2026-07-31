from app.schemas.item import DEFAULT_WASH_INTERVALS, default_wash_interval
from app.services.ai_service import VALID_TYPES, AIService, ClothingTags
from app.utils.item_naming import (
    descriptive_item_name,
    format_brand,
    is_vague_name,
    resolve_item_name,
)
from app.workers.tagging import tags_to_item_fields


class TestFormatBrand:
    def test_preserves_acronyms(self):
        assert format_brand("YSL") == "YSL"
        assert format_brand("H&M") == "H&M"

    def test_normalizes_known_lowercase_brands(self):
        assert format_brand("ysl") == "YSL"
        assert format_brand("h&m") == "H&M"
        assert format_brand("dior") == "Dior"

    def test_preserves_mixed_case_product_names(self):
        assert format_brand("Dior Sauvage") == "Dior Sauvage"
        assert format_brand("McQueen") == "McQueen"


class TestDescriptiveItemName:
    def test_cologne_uses_brand_and_product_not_color_fit(self):
        name = descriptive_item_name(
            brand="Dior",
            primary_color="black",
            fit="slim",
            item_type="cologne",
            subtype="Sauvage",
        )
        assert name == "Dior Sauvage"

    def test_cologne_brand_plus_type_when_no_product(self):
        name = descriptive_item_name(brand="YSL", item_type="cologne")
        assert name == "YSL Cologne"

    def test_apparel_includes_color_and_type(self):
        name = descriptive_item_name(
            brand="Uniqlo",
            primary_color="navy",
            fit="regular",
            item_type="shirt",
        )
        assert name == "Uniqlo Navy Regular Shirt"

    def test_sneakers_skip_fit(self):
        name = descriptive_item_name(
            brand="Nike",
            primary_color="white",
            fit="slim",
            item_type="sneakers",
            subtype="low-top",
        )
        assert name == "Nike White Low-Top"
        assert "Slim" not in name

    def test_does_not_title_case_acronym_brands(self):
        name = descriptive_item_name(brand="YSL", primary_color="black", item_type="sneakers")
        assert name == "YSL Black Sneakers"


class TestResolveItemName:
    def test_prefers_assistant_product_name_over_mechanical(self):
        resolved = resolve_item_name(
            preferred="Dior Sauvage",
            existing=None,
            brand="Dior",
            primary_color="black",
            item_type="cologne",
        )
        assert resolved == "Dior Sauvage"

    def test_keeps_existing_when_assistant_vague(self):
        resolved = resolve_item_name(
            preferred="cologne",
            existing="Dior Sauvage",
            brand="Dior",
            primary_color="black",
            item_type="cologne",
        )
        assert resolved == "Dior Sauvage"

    def test_falls_back_to_descriptive(self):
        resolved = resolve_item_name(
            preferred=None,
            existing=None,
            brand="Nike",
            primary_color="white",
            item_type="sneakers",
        )
        assert resolved == "Nike White Sneakers"

    def test_vague_detection(self):
        assert is_vague_name(None)
        assert is_vague_name("cologne", "cologne")
        assert not is_vague_name("Dior Sauvage", "cologne")


class TestWashDefaults:
    def test_footwear_and_cologne_not_tracked(self):
        for item_type in ("shoes", "sneakers", "boots", "sandals", "cologne", "accessories"):
            assert default_wash_interval(item_type) is None

    def test_unknown_and_other_not_tracked(self):
        assert default_wash_interval("unknown") is None
        assert default_wash_interval("other") is None
        assert default_wash_interval("made-up-type") is None

    def test_apparel_still_tracked(self):
        assert default_wash_interval("t-shirt") == 1
        assert default_wash_interval("jeans") == 6
        assert default_wash_interval("polo") == 2
        assert default_wash_interval("socks") == 1
        assert default_wash_interval("cardigan") == 5

    def test_all_valid_types_have_explicit_entries(self):
        missing = VALID_TYPES - set(DEFAULT_WASH_INTERVALS)
        assert missing == set(), f"VALID_TYPES missing wash defaults: {missing}"


class TestTagsToItemFieldsNaming:
    def test_sets_brand_and_product_name_for_cologne(self):
        tags = ClothingTags(
            type="cologne",
            brand="Dior",
            name="Dior Sauvage",
            primary_color="black",
            subtype="eau-de-parfum",
        )
        fields = tags_to_item_fields(tags)
        assert fields["brand"] == "Dior"
        assert fields["name"] == "Dior Sauvage"
        assert fields["type"] == "cologne"

    def test_builds_fallback_name_from_brand_when_name_missing(self):
        tags = ClothingTags(type="sneakers", brand="Nike", primary_color="white")
        fields = tags_to_item_fields(tags)
        assert fields["name"] == "Nike White Sneakers"


class TestParseBrandAndName:
    def test_parse_cologne_brand_and_name(self):
        service = AIService()
        tags = service._parse_tags_from_response(
            """
            {
                "type": "cologne",
                "brand": "YSL",
                "name": "YSL Y Eau de Parfum",
                "primary_color": "black",
                "subtype": "eau-de-parfum"
            }
            """
        )
        assert tags.type == "cologne"
        assert tags.brand == "YSL"
        assert tags.name == "YSL Y Eau de Parfum"

    def test_parse_perfume_alias_to_cologne(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": "perfume", "primary_color": "gold"}')
        assert tags.type == "cologne"
