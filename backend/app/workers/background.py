import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.item import ClothingItem
from app.services.image_service import ImageService
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def remove_item_background_job(ctx: dict, item_id: str, image_path: str) -> dict[str, Any]:
    """Produce a transparent PNG cutout for an item's image, in the background.

    Cosmetic-only and independent of AI tagging: unlike `tag_item_image`, a
    failure here must never touch `ClothingItem.status` - the item stays fully
    usable either way, this just quietly doesn't get a cleaned-up thumbnail.

    Args:
        ctx: arq context
        item_id: UUID of the item to process
        image_path: relative path to the item's original image (`item.image_path`,
            e.g. "user_id/filename.jpg") - resolved against STORAGE_PATH by
            ImageService, same as the manual /remove-background endpoint.
    """
    # Brief retries cover the remaining race where a job was already in Redis
    # before the upload request committed (common on bulk upload).
    item = None
    db = get_db_session(ctx)
    try:
        for attempt in range(5):
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item is not None:
                break
            await asyncio.sleep(0.5 * (attempt + 1))
            await db.rollback()

        if item is None:
            logger.warning(f"Background removal job: item {item_id} not found")
            return {"status": "error", "error": "Item not found", "item_id": item_id}

        try:
            image_service = ImageService()
            # remove_background is a blocking PIL/rembg call - offload it so it
            # doesn't stall this worker's event loop (same pattern as the manual
            # /remove-background endpoint). Default: transparent PNG cutout.
            # Safe to re-run: ImageService keeps the first backup and always
            # remasks from that original, so bulk cleanup can upgrade older
            # white-composited JPEGs without losing the true source photo.
            processed = await asyncio.to_thread(
                image_service.remove_background, item.image_path or image_path
            )
        except Exception as e:
            logger.warning(f"Background removal failed for item {item_id}: {e}")
            return {"status": "error", "error": str(e), "item_id": item_id}

        item.image_path = processed["image_path"]
        item.medium_path = processed["medium_path"]
        item.thumbnail_path = processed["thumbnail_path"]
        item.original_image_path = processed["original_backup_path"]
        await db.commit()
        logger.info(f"Removed background for item {item_id}")
        return {"status": "success", "item_id": item_id}
    finally:
        await db.close()


async def ai_catalog_cutout_job(ctx: dict, item_id: str, image_path: str) -> dict[str, Any]:
    """Paid AI catalog cutout for an item (OpenAI images.edit + chroma key).

    Cosmetic-only — never touches ClothingItem.status. Failures are logged and
    returned; moderation / Image API user errors are not blindly retried by
    raising (arq would re-queue).
    """
    item = None
    db = get_db_session(ctx)
    try:
        for attempt in range(5):
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item is not None:
                break
            await asyncio.sleep(0.5 * (attempt + 1))
            await db.rollback()

        if item is None:
            logger.warning(f"AI catalog cutout job: item {item_id} not found")
            return {"status": "error", "error": "Item not found", "item_id": item_id}

        try:
            from app.services.ai_catalog_cutout import AICatalogCutoutError

            image_service = ImageService()
            processed = await asyncio.to_thread(
                image_service.ai_catalog_cutout, item.image_path or image_path
            )
        except AICatalogCutoutError as e:
            # Surface moderation / user errors clearly; do not raise (no blind retries).
            logger.warning(
                "AI catalog cutout rejected for item %s [%s]: %s",
                item_id,
                e.code,
                e,
            )
            return {
                "status": "error",
                "error": str(e),
                "code": e.code,
                "item_id": item_id,
            }
        except Exception as e:
            logger.warning(f"AI catalog cutout failed for item {item_id}: {e}")
            return {"status": "error", "error": str(e), "item_id": item_id}

        item.image_path = processed["image_path"]
        item.medium_path = processed["medium_path"]
        item.thumbnail_path = processed["thumbnail_path"]
        item.original_image_path = processed["original_backup_path"]
        await db.commit()
        logger.info(f"AI catalog cutout completed for item {item_id}")
        return {"status": "success", "item_id": item_id}
    finally:
        await db.close()
