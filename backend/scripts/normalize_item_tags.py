#!/usr/bin/env python3
"""
One-off data cleanup for clothing_items with non-canonical or outright wrong tags.

Two passes:

1. General normalization — collapses known type/color aliases (e.g. "grey" -> "gray",
   "tee" -> "t-shirt", "fragrance" -> "cologne") using the same alias tables the
   manual-edit API now applies going forward (see app.utils.clothing). Safe to
   re-run; a no-op once everything is normalized.

2. Targeted corrections — a small, explicit list of items whose color/type/description
   was flatly wrong (verified against the source photo, not just non-canonical
   spelling), from a one-time manual audit. Each entry documents what was wrong and
   why. Matched by item id, so this section is inherently a one-time fix, not a rule.

Usage:
    docker compose exec backend python scripts/normalize_item_tags.py [--dry-run]

Or in production:
    docker compose -f docker-compose.prod.yml exec backend python scripts/normalize_item_tags.py [--dry-run]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.item import ClothingItem
from app.utils.clothing import normalize_color, normalize_type

# Manual corrections found 2026-07-28 by comparing each item's stored tags against
# its actual photo. Keyed by item id; only the fields that were actually wrong are
# listed. Re-running this script after these rows are already fixed is a no-op
# (values are simply set again to the same thing).
MANUAL_CORRECTIONS: dict[str, dict] = {
    # "Hollister Extremely Baggy And Oversized" — a tan/khaki McLaren graphic tee,
    # tagged type="unknown" (excluded from every outfit suggestion) with
    # primary_color="gray" even though the shirt itself is clearly tan/beige, not
    # gray; only the logo has white/red in it.
    "a60749e6-b0a2-4b4d-a6e0-c14fafa38406": {
        "type": "t-shirt",
        "subtype": "graphic tee",
        "primary_color": "tan",
        "colors": ["tan", "white", "red"],
        "ai_description": (
            "Tan short-sleeve crewneck T-shirt with a small red-and-white McLaren logo "
            "on the chest."
        ),
    },
    # "Hollister Brown Pants" (subtype "parachute pants") — actually a pair of taupe/
    # light-gray corduroy-look joggers, not brown. The existing ai_description
    # ("Gray jogger pants...") already matched the photo; only the color tag was wrong.
    "2f3616f0-62e9-4a7c-ae00-aea7ec59ea82": {
        "subtype": "joggers",
        "primary_color": "gray",
        "colors": ["gray"],
    },
    # "Zudio Dark Brown Pants" (subtype "short") — full-length olive/gray-green cargo
    # joggers, not shorts and not brown. subtype="short" was actively misleading (the
    # AI/RULES prompt reads subtype as a hint for the garment).
    "0f46d43d-a3a4-4923-afe7-123e43a0b5be": {
        "subtype": "joggers",
        "primary_color": "olive",
        "colors": ["olive"],
    },
    # "Yeezy 450 Dark Grey" — the shoe is dark maroon-brown, not charcoal/gray. The
    # existing ai_description ("Dark brown knit sneakers...") already matched the
    # photo; only the color tag was wrong.
    "50fa3e2a-13dd-4dcd-a911-180e046d900f": {
        "primary_color": "brown",
        "colors": ["brown"],
    },
    # "Yeezy Grey Shoes" — colors included "beluga", a sneaker colorway nickname, not
    # a real color value; collapsed into the existing gray + added black for the
    # visible dark sole/heel accents.
    "876adcbc-a07c-4db3-871c-ff8f93a92f75": {
        "colors": ["gray", "black"],
    },
    # "5Ivepillars Brown Relaxed Hoodie" — colors included "cream-yellow", not a real
    # color value; the ai_description ("white 'ALHAAMDULLAH' chest lettering") points
    # to white, not yellow.
    "f66b572f-2f9d-42e0-8245-daa8dc003d27": {
        "colors": ["brown", "cream", "white"],
    },
}


async def normalize_all():
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        result = await db.execute(select(ClothingItem))
        items = list(result.scalars().all())
        print(f"Found {len(items)} items\n")

        alias_fixed = 0
        manual_fixed = 0

        for item in items:
            changed = []

            # Pass 1: alias normalization
            new_type = normalize_type(item.type)
            if new_type != item.type:
                changed.append(f"type: {item.type!r} -> {new_type!r}")
                item.type = new_type

            new_color = normalize_color(item.primary_color)
            if new_color != item.primary_color:
                changed.append(f"primary_color: {item.primary_color!r} -> {new_color!r}")
                item.primary_color = new_color

            if item.colors:
                # Dedupe after normalization (order-preserving) — e.g. ["beluga",
                # "grey"] both alias to "gray" and would otherwise leave a duplicate.
                seen: set[str] = set()
                new_colors = []
                for c in (normalize_color(c) for c in item.colors):
                    if c not in seen:
                        seen.add(c)
                        new_colors.append(c)
                if new_colors != item.colors:
                    changed.append(f"colors: {item.colors!r} -> {new_colors!r}")
                    item.colors = new_colors

            if changed:
                alias_fixed += 1
                print(f"[{item.id}] {item.name or 'unnamed'}")
                for c in changed:
                    print(f"    {c}")

            # Pass 2: manual, evidence-based corrections
            correction = MANUAL_CORRECTIONS.get(str(item.id))
            if correction:
                manual_changed = []
                for field, value in correction.items():
                    current = getattr(item, field, None)
                    if current != value:
                        manual_changed.append(f"{field}: {current!r} -> {value!r}")
                        setattr(item, field, value)
                if manual_changed:
                    manual_fixed += 1
                    print(f"[{item.id}] {item.name or 'unnamed'} (manual correction)")
                    for c in manual_changed:
                        print(f"    {c}")

        print(f"\nAlias-normalized: {alias_fixed} item(s)")
        print(f"Manually corrected: {manual_fixed} item(s)")

        if dry_run:
            print("\nDry run — rolling back, no changes saved.")
            await db.rollback()
        else:
            await db.commit()
            print("\nChanges committed.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(normalize_all())
