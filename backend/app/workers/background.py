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
    """Composite an item's image onto a uniform white background, in the background.

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

        # Skip if this item has already been processed (or the user restored an
        # original) so an automatic/backfill run never clobbers a manual restore.
        if item.original_image_path:
            return {"status": "skipped", "reason": "already processed", "item_id": item_id}

        try:
            image_service = ImageService()
            # remove_background is a blocking PIL/rembg call - offload it so it
            # doesn't stall this worker's event loop (same pattern as the manual
            # /remove-background endpoint).
            processed = await asyncio.to_thread(
                image_service.remove_background, image_path, (255, 255, 255)
            )
        except Exception as e:
            logger.warning(f"Background removal failed for item {item_id}: {e}")
            return {"status": "error", "error": str(e), "item_id": item_id}

        item.original_image_path = processed["original_backup_path"]
        await db.commit()
        logger.info(f"Removed background for item {item_id}")
        return {"status": "success", "item_id": item_id}
    finally:
        await db.close()
