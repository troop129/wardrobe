import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.item import ClothingItem
from app.services.image_service import ImageService
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def remove_item_background_job(ctx: dict, item_id: str, image_path: str) -> dict:
    """
    Remove background from an item image and composite onto white.
    Cosmetic only — never changes item status on failure.
    """
    logger.info("Starting background removal for item %s", item_id)

    db = get_db_session(ctx)
    try:
        result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning("Background removal: item not found %s", item_id)
            return {"status": "skipped", "reason": "item not found"}

        if item.original_image_path:
            logger.info("Background removal skipped for %s (already processed or restored)", item_id)
            return {"status": "skipped", "reason": "already has original backup"}

        settings = get_settings()
        relative_path = image_path
        if image_path.startswith(settings.storage_path):
            prefix = settings.storage_path.rstrip("/") + "/"
            relative_path = image_path[len(prefix) :]

        image_service = ImageService()

        def _run() -> dict:
            return image_service.remove_background(relative_path, bg_color=(255, 255, 255))

        try:
            removal_result = await asyncio.to_thread(_run)
        except ImportError:
            logger.warning("Background removal unavailable (rembg not installed) for item %s", item_id)
            return {"status": "skipped", "reason": "provider unavailable"}
        except Exception as e:
            logger.exception("Background removal failed for item %s: %s", item_id, e)
            return {"status": "error", "error": str(e)}

        item.original_image_path = removal_result["original_backup_path"]
        await db.commit()
        logger.info("Background removal complete for item %s", item_id)
        return {"status": "success", "item_id": item_id}
    finally:
        await db.close()
