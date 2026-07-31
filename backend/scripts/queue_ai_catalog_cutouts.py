#!/usr/bin/env python3
"""Queue AI catalog cutout jobs for items that have not had one yet.

Default: items with an image where ai_catalog_cutout is false.
Use --all-with-images to re-run on every item (uses _orig backup as source).

Usage (homelab):
    docker exec wardrobe-backend python scripts/queue_ai_catalog_cutouts.py
    docker exec wardrobe-backend python scripts/queue_ai_catalog_cutouts.py --dry-run
    docker exec wardrobe-backend python scripts/queue_ai_catalog_cutouts.py --all-with-images
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from arq import create_pool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.item import ClothingItem
from app.services import ai_catalog_cutout
from app.workers.settings import get_redis_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List items that would be queued without enqueueing",
    )
    parser.add_argument(
        "--all-with-images",
        action="store_true",
        help="Queue every item with an image (re-runs allowed; uses _orig backup)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max items to queue (0 = no limit)",
    )
    args = parser.parse_args()

    if not ai_catalog_cutout.is_available():
        print("ERROR: AI catalog cutout is not configured (need AI_IMAGE_API_KEY or AI_API_KEY)")
        return 1

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        query = select(ClothingItem).where(ClothingItem.image_path.isnot(None))
        if not args.all_with_images:
            query = query.where(ClothingItem.ai_catalog_cutout.is_(False))
        query = query.order_by(ClothingItem.created_at.asc())
        if args.limit > 0:
            query = query.limit(args.limit)

        result = await db.execute(query)
        items = list(result.scalars().all())

    mode = "all-with-images" if args.all_with_images else "ai_catalog_cutout=false"
    print(f"Candidates: {len(items)} (mode={mode})")
    if not items:
        await engine.dispose()
        return 0

    if args.dry_run:
        for item in items:
            print(
                f"  would queue {item.id}  image={item.image_path}  "
                f"ai_catalog_cutout={item.ai_catalog_cutout}"
            )
        await engine.dispose()
        return 0

    redis = await create_pool(get_redis_settings())
    queued = 0
    failed = 0
    try:
        for item in items:
            try:
                job = await redis.enqueue_job(
                    "ai_catalog_cutout_job",
                    str(item.id),
                    item.image_path,
                    _queue_name="arq:tagging",
                )
                queued += 1
                print(f"queued {item.id} job={job.job_id}")
            except Exception as e:
                failed += 1
                print(f"FAILED {item.id}: {e}")
    finally:
        await redis.aclose()
        await engine.dispose()

    print(f"Done. queued={queued} failed={failed}")
    if queued:
        print(f"Approx cost at medium quality: ~${queued * 0.065:.2f}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
