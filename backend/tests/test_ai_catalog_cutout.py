"""Tests for AI catalog cutout (chroma key + endpoint gating)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus
from app.services import ai_catalog_cutout
from app.services.ai_catalog_cutout import (
    GREEN_KEY,
    MAGENTA_KEY,
    build_catalog_prompt,
    chroma_key_to_rgba,
    pick_chroma_key,
)


def _solid(color: tuple[int, int, int], size=(64, 64)) -> Image.Image:
    return Image.new("RGB", size, color)


class TestChromaKey:
    def test_green_key_makes_background_transparent(self):
        img = _solid(GREEN_KEY)
        # Paint an opaque red square in the center
        for y in range(20, 44):
            for x in range(20, 44):
                img.putpixel((x, y), (220, 30, 30))

        out = chroma_key_to_rgba(img, GREEN_KEY)
        assert out.mode == "RGBA"
        assert out.getpixel((2, 2))[3] == 0
        assert out.getpixel((32, 32))[3] > 200
        assert out.getpixel((32, 32))[:3] == (220, 30, 30)

    def test_magenta_key(self):
        img = _solid(MAGENTA_KEY)
        img.putpixel((32, 32), (40, 40, 40))
        out = chroma_key_to_rgba(img, MAGENTA_KEY, soft_matte=False)
        assert out.getpixel((2, 2))[3] == 0
        assert out.getpixel((32, 32))[3] == 255

    def test_pick_chroma_prefers_magenta_for_green_garment(self):
        green_shirt = _solid((30, 160, 40))
        assert pick_chroma_key(green_shirt) == MAGENTA_KEY

    def test_pick_chroma_defaults_to_green(self):
        blue_shirt = _solid((40, 60, 180))
        assert pick_chroma_key(blue_shirt) == GREEN_KEY

    def test_prompt_includes_hex(self):
        prompt = build_catalog_prompt(GREEN_KEY)
        assert "#00FF00" in prompt
        assert "catalog" in prompt.lower()


class TestAiCatalogCutoutAvailability:
    def test_disabled_without_key(self):
        settings = Settings(ai_api_key=None, ai_image_api_key=None)
        assert settings.ai_catalog_cutout_enabled is False

    def test_enabled_via_ai_api_key_fallback(self):
        settings = Settings(ai_api_key="sk-test", ai_image_api_key=None)
        assert settings.effective_ai_image_api_key == "sk-test"
        assert settings.ai_catalog_cutout_enabled is True

    def test_image_key_wins_over_ai_key(self):
        settings = Settings(ai_api_key="sk-text", ai_image_api_key="sk-image")
        assert settings.effective_ai_image_api_key == "sk-image"


class TestHealthFeaturesAiCatalog:
    @pytest.mark.asyncio
    async def test_features_includes_ai_catalog_flag(self, client: AsyncClient):
        response = await client.get("/api/v1/health/features")
        assert response.status_code == 200
        data = response.json()
        assert "background_removal" in data
        assert "ai_catalog_cutout" in data
        assert isinstance(data["ai_catalog_cutout"], bool)


class TestAiCatalogCutoutEndpoint:
    @pytest.mark.asyncio
    async def test_not_configured_returns_501(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            "app.services.ai_catalog_cutout.is_available",
            lambda: False,
        )
        response = await client.post(
            f"/api/v1/items/{uuid4()}/ai-catalog-cutout",
            headers=auth_headers,
        )
        assert response.status_code == 501

    @pytest.mark.asyncio
    async def test_item_not_found(self, client: AsyncClient, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_catalog_cutout.is_available",
            lambda: True,
        )
        response = await client.post(
            f"/api/v1/items/{uuid4()}/ai-catalog-cutout",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_item_no_image(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, monkeypatch
    ):
        monkeypatch.setattr(
            "app.services.ai_catalog_cutout.is_available",
            lambda: True,
        )
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(
            f"/api/v1/items/{item.id}/ai-catalog-cutout",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "no image" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_queues_job(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, monkeypatch
    ):
        monkeypatch.setattr(
            "app.services.ai_catalog_cutout.is_available",
            lambda: True,
        )
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"{test_user.id}/photo.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        mock_redis = AsyncMock()
        mock_redis.enqueue_job.return_value = MagicMock(job_id="job-cutout-1")
        mock_redis.aclose = AsyncMock()

        with patch("app.api.items.create_pool", AsyncMock(return_value=mock_redis)):
            response = await client.post(
                f"/api/v1/items/{item.id}/ai-catalog-cutout",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["job_id"] == "job-cutout-1"
        mock_redis.enqueue_job.assert_called_once()
        assert mock_redis.enqueue_job.call_args.args[0] == "ai_catalog_cutout_job"

    @pytest.mark.asyncio
    async def test_unauthenticated(self, client: AsyncClient):
        response = await client.post(f"/api/v1/items/{uuid4()}/ai-catalog-cutout")
        assert response.status_code == 401


class TestImageServiceAiCatalogCutout:
    @pytest.mark.asyncio
    async def test_saves_transparent_png_and_backup(self, tmp_path, monkeypatch):
        from app.services.image_service import ImageService

        storage = tmp_path / "storage"
        storage.mkdir()
        svc = ImageService(storage_path=str(storage))

        user_dir = storage / "user1"
        user_dir.mkdir()
        rel = "user1/shirt.jpg"
        Image.new("RGB", (200, 200), (40, 80, 180)).save(storage / rel, format="JPEG")

        # Fake OpenAI edit → solid green with a blue garment square
        chroma = Image.new("RGB", (256, 256), GREEN_KEY)
        for y in range(60, 196):
            for x in range(60, 196):
                chroma.putpixel((x, y), (30, 60, 200))
        chroma.info["chroma_key"] = GREEN_KEY

        monkeypatch.setattr(
            ai_catalog_cutout,
            "edit_to_chroma_catalog",
            lambda _path: chroma,
        )

        result = svc.ai_catalog_cutout(rel)
        assert result["image_path"].endswith(".png")
        assert result["original_backup_path"].endswith("_orig.jpg")
        assert (storage / result["original_backup_path"]).exists()
        out = Image.open(storage / result["image_path"])
        assert out.mode == "RGBA"
        assert out.getpixel((2, 2))[3] == 0
