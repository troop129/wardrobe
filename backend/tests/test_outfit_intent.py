from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
from app.models.learning import ItemPairScore
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus, UserFeedback


async def _create_pending_outfit(db_session, user_id):
    items = []
    for item_type in ("t-shirt", "pants", "sneakers"):
        item = ClothingItem(
            user_id=user_id,
            type=item_type,
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        items.append(item)
    await db_session.flush()

    outfit = Outfit(
        user_id=user_id,
        occasion="casual",
        scheduled_for=date.today(),
        status=OutfitStatus.pending,
        source=OutfitSource.on_demand,
    )
    for position, item in enumerate(items):
        outfit.items.append(OutfitItem(item_id=item.id, position=position))
    db_session.add(outfit)
    await db_session.commit()
    await db_session.refresh(outfit)
    return outfit, items


@pytest.mark.asyncio
async def test_accept_and_reject_persist_idempotent_intent(
    client, test_user, auth_headers, db_session
):
    outfit, items = await _create_pending_outfit(db_session, test_user.id)

    first = await client.post(f"/api/v1/outfits/{outfit.id}/accept", headers=auth_headers)
    second = await client.post(f"/api/v1/outfits/{outfit.id}/accept", headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "accepted"

    feedback_result = await db_session.execute(
        select(UserFeedback).where(UserFeedback.outfit_id == outfit.id)
    )
    feedback = feedback_result.scalar_one()
    assert feedback.accepted is True

    for item in items:
        await db_session.refresh(item)
        assert item.acceptance_count == 1

    rejected = await client.post(f"/api/v1/outfits/{outfit.id}/reject", headers=auth_headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    await db_session.refresh(feedback)
    assert feedback.accepted is False
    for item in items:
        await db_session.refresh(item)
        assert item.acceptance_count == 0


@pytest.mark.asyncio
async def test_skip_is_neutral_and_closes_pending_outfit(
    client, test_user, auth_headers, db_session
):
    outfit, _ = await _create_pending_outfit(db_session, test_user.id)

    response = await client.post(f"/api/v1/outfits/{outfit.id}/skip", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"

    feedback_result = await db_session.execute(
        select(UserFeedback).where(UserFeedback.outfit_id == outfit.id)
    )
    assert feedback_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_detailed_feedback_keeps_acceptance_counts_idempotent(
    client, test_user, auth_headers, db_session
):
    outfit, items = await _create_pending_outfit(db_session, test_user.id)

    accepted = await client.post(
        f"/api/v1/outfits/{outfit.id}/feedback",
        headers=auth_headers,
        json={"accepted": True},
    )
    repeated = await client.post(
        f"/api/v1/outfits/{outfit.id}/feedback",
        headers=auth_headers,
        json={"accepted": True},
    )

    assert accepted.status_code == 200
    assert repeated.status_code == 200
    for item in items:
        await db_session.refresh(item)
        assert item.acceptance_count == 1

    rejected = await client.post(
        f"/api/v1/outfits/{outfit.id}/feedback",
        headers=auth_headers,
        json={"accepted": False},
    )
    assert rejected.status_code == 200
    for item in items:
        await db_session.refresh(item)
        assert item.acceptance_count == 0


@pytest.mark.asyncio
async def test_keep_together_creates_immediate_idempotent_pair_preferences(
    client, test_user, auth_headers, db_session
):
    outfit, _ = await _create_pending_outfit(db_session, test_user.id)

    first = await client.post(f"/api/v1/outfits/{outfit.id}/keep-together", headers=auth_headers)
    repeated = await client.post(f"/api/v1/outfits/{outfit.id}/keep-together", headers=auth_headers)

    assert first.status_code == 200
    assert first.json()["saved_pairs"] == 3
    assert repeated.status_code == 200
    assert repeated.json()["saved_pairs"] == 0
    pairs = list(
        (
            await db_session.execute(
                select(ItemPairScore).where(ItemPairScore.user_id == test_user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(pairs) == 3
    assert all(pair.times_paired == 2 for pair in pairs)
    assert all(float(pair.compatibility_score) > 0.3 for pair in pairs)


@pytest.mark.asyncio
async def test_local_refinement_can_add_a_layer(client, test_user, auth_headers, db_session):
    outfit, _ = await _create_pending_outfit(db_session, test_user.id)
    jacket = ClothingItem(
        user_id=test_user.id,
        type="jacket",
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        primary_color="blue",
    )
    db_session.add(jacket)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/outfits/{outfit.id}/refine",
        headers=auth_headers,
        json={"message": "add a layer"},
    )

    assert response.status_code == 200
    assert str(jacket.id) in {item["id"] for item in response.json()["outfit"]["items"]}
    assert "Updated" in response.json()["reply"]
