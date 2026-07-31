import logging
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitStatus,
    UserFeedback,
)
from app.models.user import User
from app.services.ai_service import AIDisabledError
from app.services.item_service import ItemService
from app.services.learning_service import LearningService
from app.services.outfit_service import OutfitListFilters, OutfitService
from app.services.recommendation_service import (
    AIRecommendationError,
    InsufficientWardrobeError,
    RecommendationService,
)
from app.services.studio_service import (
    ItemOwnershipError,
    OutfitNotTemplateError,
    OutfitWornImmutableError,
    StudioService,
)
from app.services.suggestion_cache import clear_suggestions
from app.services.weather_service import WeatherData
from app.utils.auth import get_current_user
from app.utils.clothing import ITEM_ROLE
from app.utils.rate_limit import rate_limit_by_user
from app.utils.signed_urls import sign_image_url

logger = logging.getLogger(__name__)

VALID_OCCASIONS = {
    "casual",
    "office",
    "work",
    "formal",
    "smart-casual",
    "business-casual",
    "date",
    "party",
    "sporty",
    "sport",
    "outdoor",
    "travel",
    "lounge",
    "beach",
    "interview",
    "wedding",
    "dinner",
    "brunch",
    "gym",
    "running",
    "hiking",
    "weekend",
}


def get_user_today(user: User) -> date:
    try:
        user_tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")
    return datetime.now(UTC).astimezone(user_tz).date()


router = APIRouter(prefix="/outfits", tags=["Outfits"])


class WeatherOverrideRequest(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    feels_like: float | None = Field(None, description="Feels like temperature")
    condition: str = Field(default="unknown", description="Weather condition")
    precipitation_chance: int = Field(default=0, ge=0, le=100)
    humidity: int = Field(default=50, ge=0, le=100)


class SuggestRequest(BaseModel):
    occasion: str | None = None

    @field_validator("occasion")
    @classmethod
    def validate_occasion(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if len(v) > 50:
            raise ValueError("Occasion must be 50 characters or less")
        if v not in VALID_OCCASIONS:
            raise ValueError(
                f"Invalid occasion '{v}'. Must be one of: {', '.join(sorted(VALID_OCCASIONS))}"
            )
        return v

    time_of_day: Literal["morning", "afternoon", "evening", "night", "full day"] | None = None
    weather_override: WeatherOverrideRequest | None = None
    exclude_items: list[UUID] = Field(default_factory=list, description="Items to exclude")
    include_items: list[UUID] = Field(default_factory=list, description="Items to include")
    strategy: Literal["rules", "ai"] = "rules"


class OutfitItemResponse(BaseModel):
    id: UUID
    type: str
    subtype: str | None = None
    name: str | None = None
    brand: str | None = None
    primary_color: str | None = None
    colors: list[str] = []
    tags: dict = Field(default_factory=dict)
    image_path: str | None = None
    thumbnail_path: str | None = None
    layer_type: str | None = None
    position: int

    @computed_field
    @property
    def image_url(self) -> str | None:
        if self.image_path:
            return sign_image_url(self.image_path)
        return None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class WoreInsteadItem(BaseModel):
    id: UUID
    type: str
    name: str | None = None
    thumbnail_path: str | None = None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class FeedbackSummary(BaseModel):
    rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None
    actually_worn: bool | None = None
    wore_instead_items: list[WoreInsteadItem] | None = None


class FamilyRatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5, description="Rating 1-5")
    comment: str | None = Field(None, max_length=500)


class FamilyRatingResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_display_name: str
    user_avatar_url: str | None = None
    rating: int
    comment: str | None = None
    created_at: datetime


class OutfitResponse(BaseModel):
    id: UUID
    occasion: str
    scheduled_for: date | None = None
    status: str
    name: str | None = None
    replaces_outfit_id: UUID | None = None
    cloned_from_outfit_id: UUID | None = None
    source: str
    reasoning: str | None = None
    style_notes: str | None = None
    highlights: list[str] | None = None
    weather: dict | None = None
    items: list[OutfitItemResponse]
    feedback: FeedbackSummary | None = None
    family_ratings: list[FamilyRatingResponse] | None = None
    family_rating_average: float | None = None
    family_rating_count: int | None = None
    is_starter_suggestion: bool = False
    created_at: datetime


class OutfitListResponse(BaseModel):
    outfits: list[OutfitResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class BulkOutfitFilters(BaseModel):
    status_filter: str | None = Field(None, alias="status")
    occasion: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    source: str | None = None
    is_lookbook: bool | None = None
    is_replacement: bool | None = None
    has_source_item: bool | None = None
    item_type: str | None = None
    search: str | None = None
    cloned_from_outfit_id: UUID | None = None


class BulkDeleteOutfitsRequest(BaseModel):
    # Explicit selection
    outfit_ids: list[UUID] | None = None

    # Select all with exceptions
    select_all: bool = False
    excluded_ids: list[UUID] | None = None
    filters: BulkOutfitFilters | None = None

    def model_post_init(self, __context):
        if not self.select_all and not self.outfit_ids:
            raise ValueError("Either outfit_ids or select_all=True must be provided")
        if self.select_all and self.outfit_ids:
            raise ValueError("Cannot use both outfit_ids and select_all")


class BulkDeleteOutfitsResponse(BaseModel):
    deleted: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    accepted: bool | None = Field(None, description="Whether outfit was accepted")
    rating: int | None = Field(None, ge=1, le=5, description="Overall rating 1-5")
    comfort_rating: int | None = Field(None, ge=1, le=5, description="Comfort rating 1-5")
    style_rating: int | None = Field(None, ge=1, le=5, description="Style rating 1-5")
    comment: str | None = Field(None, max_length=1000, description="Optional comment")
    worn: bool | None = Field(None, description="Whether the outfit was worn")
    worn_with_modifications: bool | None = Field(
        None, description="If worn, whether modifications were made"
    )
    modification_notes: str | None = Field(None, max_length=500)
    actually_worn: bool | None = Field(
        None, description="Did user actually wear this recommendation?"
    )
    wore_instead_items: list[UUID] | None = Field(
        None, description="Item IDs user wore instead of recommendation"
    )


class FeedbackResponse(BaseModel):
    id: UUID
    outfit_id: UUID
    accepted: bool | None = None
    rating: int | None = None
    comfort_rating: int | None = None
    style_rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None
    worn_with_modifications: bool = False
    modification_notes: str | None = None
    actually_worn: bool | None = None
    wore_instead_items: list[UUID] | None = None
    created_at: datetime


async def fetch_wore_instead_items_map(
    db: AsyncSession, outfits: list[Outfit], user_id: UUID | None = None
) -> dict[str, list[WoreInsteadItem]]:
    all_item_ids: set[UUID] = set()
    outfit_to_item_ids: dict[str, list[str]] = {}

    for outfit in outfits:
        if outfit.feedback and outfit.feedback.wore_instead_items:
            item_ids: list[str] = []
            for item_data in outfit.feedback.wore_instead_items:
                try:
                    if isinstance(item_data, dict):
                        item_id = item_data.get("item_id", "")
                    else:
                        item_id = str(item_data)
                    if item_id:
                        item_ids.append(item_id)
                        all_item_ids.add(UUID(item_id))
                except (ValueError, TypeError, KeyError):
                    continue
            outfit_to_item_ids[str(outfit.id)] = item_ids

    if not all_item_ids:
        return {}

    query = select(ClothingItem).where(ClothingItem.id.in_(all_item_ids))
    if user_id is not None:
        query = query.where(ClothingItem.user_id == user_id)
    result = await db.execute(query)
    items_by_id = {str(item.id): item for item in result.scalars().all()}

    wore_instead_map: dict[str, list[WoreInsteadItem]] = {}
    for outfit_id, item_ids in outfit_to_item_ids.items():
        wore_items = []
        for item_id in item_ids:
            if item_id in items_by_id:
                item = items_by_id[item_id]
                wore_items.append(
                    WoreInsteadItem(
                        id=item.id,
                        type=item.type,
                        name=item.name,
                        thumbnail_path=item.thumbnail_path,
                    )
                )
        if wore_items:
            wore_instead_map[outfit_id] = wore_items

    return wore_instead_map


def outfit_to_response(
    outfit: Outfit,
    wore_instead_items_map: dict[str, list[WoreInsteadItem]] | None = None,
    is_starter_suggestion: bool = False,
) -> OutfitResponse:
    items = []
    for outfit_item in sorted(outfit.items, key=lambda x: x.position):
        item = outfit_item.item
        items.append(
            OutfitItemResponse(
                id=item.id,
                type=item.type,
                subtype=item.subtype,
                name=item.name,
                brand=item.brand,
                primary_color=item.primary_color,
                colors=item.colors or [],
                tags=item.tags or {},
                image_path=item.image_path,
                thumbnail_path=item.thumbnail_path,
                layer_type=outfit_item.layer_type,
                position=outfit_item.position,
            )
        )

    feedback_summary = None
    if outfit.feedback:
        wore_instead = None
        if wore_instead_items_map and str(outfit.id) in wore_instead_items_map:
            wore_instead = wore_instead_items_map[str(outfit.id)]
        feedback_summary = FeedbackSummary(
            rating=outfit.feedback.rating,
            comment=outfit.feedback.comment,
            worn_at=outfit.feedback.worn_at,
            actually_worn=outfit.feedback.actually_worn,
            wore_instead_items=wore_instead,
        )

    highlights = None
    if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
        raw_highlights = outfit.ai_raw_response.get("highlights")
        if raw_highlights and isinstance(raw_highlights, list):
            highlights = raw_highlights

    family_ratings_list = None
    family_rating_average = None
    family_rating_count = None
    if hasattr(outfit, "family_ratings") and outfit.family_ratings:
        family_ratings_list = [
            FamilyRatingResponse(
                id=r.id,
                user_id=r.user_id,
                user_display_name=(r.user.display_name or r.user.email) if r.user else "Unknown",
                user_avatar_url=r.user.avatar_url if r.user else None,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at,
            )
            for r in outfit.family_ratings
        ]
        family_rating_count = len(outfit.family_ratings)
        if family_rating_count > 0:
            family_rating_average = (
                sum(r.rating for r in outfit.family_ratings) / family_rating_count
            )

    return OutfitResponse(
        id=outfit.id,
        occasion=outfit.occasion,
        scheduled_for=outfit.scheduled_for,
        status=outfit.status.value,
        name=outfit.name,
        replaces_outfit_id=outfit.replaces_outfit_id,
        cloned_from_outfit_id=outfit.cloned_from_outfit_id,
        source=outfit.source.value,
        reasoning=outfit.reasoning,
        style_notes=outfit.style_notes,
        highlights=highlights,
        weather=outfit.weather_data,
        items=items,
        feedback=feedback_summary,
        family_ratings=family_ratings_list,
        family_rating_average=family_rating_average,
        family_rating_count=family_rating_count,
        is_starter_suggestion=is_starter_suggestion,
        created_at=outfit.created_at,
    )


async def _record_outfit_intent(
    db: AsyncSession,
    outfit: Outfit,
    *,
    accepted: bool,
) -> None:
    """Persist the lightweight accept/reject signal used by the main UI.

    Historically these endpoints only changed ``Outfit.status``. That meant the
    most common user actions never reached the learning profile, while the much
    less common detailed feedback dialog did. Keep intent separate from "worn"
    (accepting a morning suggestion is not proof it was worn), but make it a real,
    idempotent feedback signal.
    """
    previous = outfit.feedback.accepted if outfit.feedback else None
    changed = previous != accepted or outfit.status != (
        OutfitStatus.accepted if accepted else OutfitStatus.rejected
    )
    if outfit.feedback is None:
        outfit.feedback = UserFeedback(outfit_id=outfit.id)
        db.add(outfit.feedback)

    outfit.feedback.accepted = accepted
    outfit.status = OutfitStatus.accepted if accepted else OutfitStatus.rejected
    outfit.responded_at = datetime.now(UTC)

    _apply_acceptance_count_delta(outfit, previous, accepted)

    await db.commit()

    # A full profile recomputation is deterministic and safe if a tablet retries
    # a request. The incremental pair-learning path is reserved for richer
    # rating/wear feedback, where it already captures additional signal types.
    if changed:
        try:
            await LearningService(db).recompute_learning_profile(outfit.user_id)
        except Exception as e:
            logger.exception("Learning recompute failed for outfit %s: %s", outfit.id, e)


def _apply_acceptance_count_delta(
    outfit: Outfit,
    previous: bool | None,
    accepted: bool,
) -> None:
    """Keep per-item acceptance counters correct across retries and edits."""
    if previous == accepted:
        return
    delta = (1 if accepted else 0) - (1 if previous is True else 0)
    if not delta:
        return
    for outfit_item in outfit.items:
        current = outfit_item.item.acceptance_count or 0
        outfit_item.item.acceptance_count = max(0, current + delta)


@router.post("/suggest", response_model=OutfitResponse)
async def suggest_outfit(
    request: SuggestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    await rate_limit_by_user(str(current_user.id), "suggest", max_requests=10, window_seconds=60)
    weather_override = None
    if request.weather_override:
        w = request.weather_override
        weather_override = WeatherData(
            temperature=w.temperature,
            feels_like=w.feels_like or w.temperature,
            humidity=w.humidity,
            precipitation_chance=w.precipitation_chance,
            precipitation_mm=0,
            wind_speed=0,
            condition=w.condition,
            condition_code=0,
            is_day=True,
            uv_index=0,
            timestamp=datetime.utcnow(),
        )

    service = RecommendationService(db)

    occasion = request.occasion
    if occasion is None:
        if current_user.preferences and current_user.preferences.default_occasion:
            occasion = current_user.preferences.default_occasion
        else:
            occasion = "casual"

    try:
        outfit = await service.generate_recommendation(
            user=current_user,
            occasion=occasion,
            weather_override=weather_override,
            exclude_items=request.exclude_items,
            include_items=request.include_items,
            time_of_day=request.time_of_day,
            strategy=request.strategy,
        )
    except InsufficientWardrobeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except AIDisabledError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal AI is disabled; outfit suggestions are deferred to an external agent.",
        ) from None
    except AIRecommendationError as e:
        logger.error(f"AI recommendation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    item_service = ItemService(db)
    total_items = await item_service.get_ready_item_count(current_user.id)
    is_starter = total_items <= 5

    wore_instead_map = await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    return outfit_to_response(outfit, wore_instead_map, is_starter_suggestion=is_starter)


@router.get("", response_model=OutfitListResponse)
async def list_outfits(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    occasion: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    family_member_id: UUID | None = Query(None, description="View a family member's outfits"),
    source: str | None = Query(None, description="Comma-separated source enum filter"),
    is_lookbook: bool | None = Query(None, description="true for templates only"),
    is_replacement: bool | None = Query(None),
    has_source_item: bool | None = Query(None),
    item_type: str | None = Query(None),
    source_type: str | None = Query(
        None, description="Legacy alias for item_type used by /pairings"
    ),
    search: str | None = Query(None, max_length=50),
    cloned_from_outfit_id: UUID | None = Query(
        None, description="Filter to wear instances of a specific template"
    ),
) -> OutfitListResponse:
    service = OutfitService(db)

    target_user_id = current_user.id
    if family_member_id:
        target_user_id = await service.verify_family_access(current_user, family_member_id)

    filters = OutfitListFilters(
        user_id=target_user_id,
        status_filter=status_filter,
        occasion=occasion,
        date_from=date_from,
        date_to=date_to,
        source=source,
        is_lookbook=is_lookbook,
        is_replacement=is_replacement,
        has_source_item=has_source_item,
        item_type=item_type or source_type,
        family_member_view=family_member_id is not None,
        search=search,
        cloned_from_outfit_id=cloned_from_outfit_id,
    )

    outfits, total = await service.list_with_filters(filters, page, page_size)

    wore_instead_map = await fetch_wore_instead_items_map(db, outfits, user_id=current_user.id)

    outfit_responses = [outfit_to_response(o, wore_instead_map) for o in outfits]

    return OutfitListResponse(
        outfits=outfit_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.post("/bulk/delete", response_model=BulkDeleteOutfitsResponse)
async def bulk_delete_outfits(
    request: BulkDeleteOutfitsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkDeleteOutfitsResponse:
    service = OutfitService(db)
    deleted = 0
    failed = 0
    errors: list[str] = []

    if request.select_all:
        list_filters = OutfitListFilters(
            user_id=current_user.id,
            status_filter=request.filters.status_filter if request.filters else None,
            occasion=request.filters.occasion if request.filters else None,
            date_from=request.filters.date_from if request.filters else None,
            date_to=request.filters.date_to if request.filters else None,
            source=request.filters.source if request.filters else None,
            is_lookbook=request.filters.is_lookbook if request.filters else None,
            is_replacement=request.filters.is_replacement if request.filters else None,
            has_source_item=request.filters.has_source_item if request.filters else None,
            item_type=request.filters.item_type if request.filters else None,
            search=request.filters.search if request.filters else None,
            cloned_from_outfit_id=request.filters.cloned_from_outfit_id
            if request.filters
            else None,
        )
        outfit_ids = await service.get_ids_by_filter(
            list_filters,
            excluded_ids=list(request.excluded_ids) if request.excluded_ids else None,
        )
        logger.info(f"Bulk delete select_all: {len(outfit_ids)} outfits to delete")
    else:
        outfit_ids = request.outfit_ids or []

    studio = StudioService(db)
    for outfit_id in outfit_ids:
        try:
            deleted_ok = await studio.delete_outfit(current_user, outfit_id)
            if not deleted_ok:
                errors.append(f"Outfit {outfit_id} not found or not owned by user")
                failed += 1
                continue

            deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete outfit {outfit_id}: {e}")
            errors.append(f"Failed to delete outfit {outfit_id}")
            failed += 1

    await db.commit()

    return BulkDeleteOutfitsResponse(deleted=deleted, failed=failed, errors=errors)


@router.get("/{outfit_id}", response_model=OutfitResponse)
async def get_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.post("/{outfit_id}/accept", response_model=OutfitResponse)
async def accept_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    await _record_outfit_intent(db, outfit, accepted=True)

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.post("/{outfit_id}/reject", response_model=OutfitResponse)
async def reject_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    await _record_outfit_intent(db, outfit, accepted=False)

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.post("/{outfit_id}/skip", response_model=OutfitResponse)
async def skip_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    service = OutfitService(db)
    outfit = await service.set_status(outfit_id, current_user.id, OutfitStatus.skipped)
    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


class KeepTogetherResponse(BaseModel):
    saved_pairs: int
    message: str


@router.post("/{outfit_id}/keep-together", response_model=KeepTogetherResponse)
async def keep_outfit_together(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> KeepTogetherResponse:
    result = await db.execute(
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
    )
    outfit = result.scalar_one_or_none()
    if outfit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")
    saved = await LearningService(db).record_explicit_pair_preferences(outfit)
    if saved:
        await clear_suggestions(current_user.id, outfit.occasion)
    return KeepTogetherResponse(
        saved_pairs=saved,
        message=(
            f"Saved {saved} new keep-together pair{'s' if saved != 1 else ''}."
            if saved
            else "This combination was already saved."
        ),
    )


class RefineOutfitRequest(BaseModel):
    message: str = Field(min_length=2, max_length=500)


class RefineOutfitResponse(BaseModel):
    outfit: OutfitResponse
    reply: str
    saved_pairs: int = 0


_REFINE_ROLE_ALIASES = {
    "shirt": "base_top",
    "top": "base_top",
    "tee": "base_top",
    "pants": "bottom",
    "pant": "bottom",
    "jeans": "bottom",
    "bottom": "bottom",
    "shoes": "footwear",
    "shoe": "footwear",
    "sneakers": "footwear",
    "footwear": "footwear",
    "jacket": "outer_layer",
    "coat": "outer_layer",
    "layer": "outer_layer",
}


def _mentioned_refinement_items(message: str, items: list[ClothingItem]) -> list[ClothingItem]:
    mentioned = []
    for item in items:
        name = (item.name or "").lower()
        brand = (item.brand or "").lower()
        color = (item.primary_color or "").lower()
        item_type = (item.type or "").lower()
        subtype = (item.subtype or "").lower()
        named = len(name) >= 3 and name in message
        described = bool(color and color in message) and any(
            value and value in message for value in (item_type, subtype)
        )
        branded = (
            len(brand) >= 2
            and brand in message
            and any(value and value in message for value in (item_type, subtype, name))
        )
        if named or described or branded:
            mentioned.append(item)
    return mentioned


def _replace_role(
    item_ids: list[UUID], items_by_id: dict[UUID, ClothingItem], replacement: ClothingItem
):
    replacement_role = ITEM_ROLE.get((replacement.type or "").lower())
    if replacement.type == "cologne":
        return [item_id for item_id in item_ids if items_by_id[item_id].type != "cologne"] + [
            replacement.id
        ]
    if replacement_role is None or replacement_role == "accessory":
        return item_ids if replacement.id in item_ids else [*item_ids, replacement.id]
    conflicting_roles = {replacement_role}
    if replacement_role == "full_body":
        conflicting_roles.update({"base_top", "bottom"})
    elif replacement_role in {"base_top", "bottom"}:
        conflicting_roles.add("full_body")
    return [
        item_id
        for item_id in item_ids
        if ITEM_ROLE.get((items_by_id[item_id].type or "").lower()) not in conflicting_roles
    ] + [replacement.id]


@router.post("/{outfit_id}/refine", response_model=RefineOutfitResponse)
async def refine_outfit(
    outfit_id: UUID,
    request: RefineOutfitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RefineOutfitResponse:
    """Apply common natural-language outfit edits locally, without an LLM call."""
    result = await db.execute(
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
    )
    outfit = result.scalar_one_or_none()
    if outfit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")

    candidates_result = await db.execute(
        select(ClothingItem).where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
                ClothingItem.needs_wash.is_(False),
            )
        )
    )
    candidates = list(candidates_result.scalars().all())
    items_by_id = {item.id: item for item in candidates}
    for outfit_item in outfit.items:
        items_by_id[outfit_item.item_id] = outfit_item.item

    message = request.message.lower().strip()
    item_ids = [oi.item_id for oi in sorted(outfit.items, key=lambda oi: oi.position)]
    original_ids = list(item_ids)
    mentioned = _mentioned_refinement_items(message, candidates)

    remove_layers = any(
        phrase in message
        for phrase in ("no layer", "remove layer", "fewer layer", "less layer", "too hot")
    )
    if remove_layers:
        item_ids = [
            item_id
            for item_id in item_ids
            if ITEM_ROLE.get((items_by_id[item_id].type or "").lower())
            not in {"mid_layer", "outer_layer"}
        ]
    if any(
        phrase in message
        for phrase in ("no cologne", "no fragrance", "remove cologne", "remove fragrance")
    ):
        item_ids = [item_id for item_id in item_ids if items_by_id[item_id].type != "cologne"]

    # Concrete color/name/brand mentions take priority and make recognition useful
    # in ordinary language such as "use the blue Nike jacket".
    for item in mentioned:
        item_ids = _replace_role(item_ids, items_by_id, item)

    good_pairs = await RecommendationService(db)._get_good_item_pairs(current_user.id)
    current_set = set(item_ids)

    def best_for_role(role: str, *, cologne: bool = False) -> ClothingItem | None:
        pool = [
            item
            for item in candidates
            if item.id not in current_set
            and (
                item.type == "cologne"
                if cologne
                else ITEM_ROLE.get((item.type or "").lower()) == role
            )
        ]
        if not pool:
            return None
        return max(
            pool,
            key=lambda item: (
                sum(partner in current_set for partner in good_pairs.get(item.id, [])),
                item.favorite,
                item.acceptance_count or 0,
                -(item.suggestion_count or 0),
            ),
        )

    if any(phrase in message for phrase in ("add a layer", "add layer", "more layer")):
        present_roles = {
            ITEM_ROLE.get((items_by_id[item_id].type or "").lower()) for item_id in item_ids
        }
        if "outer_layer" in present_roles:
            layer = best_for_role("mid_layer")
        elif "mid_layer" in present_roles:
            layer = best_for_role("outer_layer")
        else:
            layer = best_for_role("outer_layer") or best_for_role("mid_layer")
        if layer:
            item_ids = _replace_role(item_ids, items_by_id, layer)
            current_set = set(item_ids)
    if any(phrase in message for phrase in ("add cologne", "add fragrance", "add a scent")):
        fragrance = best_for_role("accessory", cologne=True)
        if fragrance:
            item_ids = _replace_role(item_ids, items_by_id, fragrance)
            current_set = set(item_ids)

    for alias, role in _REFINE_ROLE_ALIASES.items():
        if f"different {alias}" in message or f"another {alias}" in message:
            replacement = best_for_role(role)
            if replacement:
                item_ids = _replace_role(item_ids, items_by_id, replacement)
                current_set = set(item_ids)
            break

    changed = item_ids != original_ids
    service = StudioService(db)
    if changed:
        updated = await service.patch_outfit(
            user=current_user,
            outfit_id=outfit.id,
            name=None,
            items=item_ids,
        )
        await db.commit()
    else:
        updated = outfit

    saved_pairs = 0
    wants_together = any(
        phrase in message for phrase in ("together", "i like", "would wear", "save this combo")
    )
    if wants_together:
        pair_ids = [item.id for item in mentioned] if len(mentioned) >= 2 else None
        full_updated = await service.get_full_outfit(updated.id)
        saved_pairs = await LearningService(db).record_explicit_pair_preferences(
            full_updated, pair_ids
        )
        updated = full_updated

    await clear_suggestions(current_user.id, outfit.occasion)
    full = await service.get_full_outfit(updated.id)
    if changed and saved_pairs:
        reply = f"Updated the outfit and saved {saved_pairs} keep-together pairs."
    elif changed:
        reply = "Updated the outfit using your available clean items."
    elif saved_pairs:
        reply = f"Saved {saved_pairs} keep-together pairs for future suggestions."
    else:
        reply = (
            "I could not map that to an item yet. Try ‘different shoes’, ‘add a layer’, "
            "‘no cologne’, or name a color, brand, and item type."
        )
    return RefineOutfitResponse(
        outfit=outfit_to_response(full), reply=reply, saved_pairs=saved_pairs
    )


@router.delete("/{outfit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    studio = StudioService(db)
    deleted = await studio.delete_outfit(current_user, outfit_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    await db.commit()


@router.post("/{outfit_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    outfit_id: UUID,
    request: FeedbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeedbackResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.feedback), selectinload(Outfit.items).selectinload(OutfitItem.item)
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    if outfit.feedback:
        feedback = outfit.feedback
    else:
        feedback = UserFeedback(outfit_id=outfit.id)
        outfit.feedback = feedback
        db.add(feedback)

    previous_accepted = feedback.accepted
    if request.accepted is not None:
        _apply_acceptance_count_delta(outfit, previous_accepted, request.accepted)
        feedback.accepted = request.accepted
        outfit.status = OutfitStatus.accepted if request.accepted else OutfitStatus.rejected
        outfit.responded_at = datetime.utcnow()

    if request.rating is not None:
        feedback.rating = request.rating
    if request.comfort_rating is not None:
        feedback.comfort_rating = request.comfort_rating
    if request.style_rating is not None:
        feedback.style_rating = request.style_rating
    if request.comment is not None:
        feedback.comment = request.comment
    if request.worn and not feedback.worn_at:
        user_today = get_user_today(current_user)
        feedback.worn_at = user_today
        studio_service = StudioService(db)
        await studio_service._apply_wear_tracking(
            current_user.id,
            [outfit_item.item_id for outfit_item in outfit.items],
            user_today,
            outfit_id=outfit.id,
            occasion=outfit.occasion,
        )
    if request.worn_with_modifications is not None:
        feedback.worn_with_modifications = request.worn_with_modifications
    if request.modification_notes is not None:
        feedback.modification_notes = request.modification_notes
    if request.actually_worn is not None:
        feedback.actually_worn = request.actually_worn
    if request.wore_instead_items is not None:
        feedback.wore_instead_items = [str(item_id) for item_id in request.wore_instead_items]
        if request.wore_instead_items:
            studio_service = StudioService(db)
            try:
                await studio_service.create_wore_instead(
                    user=current_user,
                    original_outfit_id=outfit_id,
                    item_ids=list(request.wore_instead_items),
                    rating=request.rating,
                    comment=request.comment,
                    scheduled_for=None,
                )
            except ItemOwnershipError:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error_code": "OUTFIT_ITEM_OWNERSHIP",
                        "message": "One or more items do not belong to you",
                    },
                ) from None

    await db.commit()
    await db.refresh(feedback)

    try:
        learning_service = LearningService(db)
        await learning_service.process_feedback(outfit_id, current_user.id)
        logger.info(f"Learning processed for outfit {outfit_id}")
    except Exception as e:
        logger.exception(f"Learning processing failed for outfit {outfit_id}: {e}")

    return FeedbackResponse(
        id=feedback.id,
        outfit_id=feedback.outfit_id,
        accepted=feedback.accepted,
        rating=feedback.rating,
        comfort_rating=feedback.comfort_rating,
        style_rating=feedback.style_rating,
        comment=feedback.comment,
        worn_at=feedback.worn_at,
        worn_with_modifications=feedback.worn_with_modifications,
        modification_notes=feedback.modification_notes,
        actually_worn=feedback.actually_worn,
        wore_instead_items=[UUID(item_id) for item_id in (feedback.wore_instead_items or [])],
        created_at=feedback.created_at,
    )


@router.get("/{outfit_id}/feedback", response_model=FeedbackResponse)
async def get_feedback(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeedbackResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(selectinload(Outfit.feedback))
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
        )

    if not outfit.feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found for this outfit",
        )

    feedback = outfit.feedback
    return FeedbackResponse(
        id=feedback.id,
        outfit_id=feedback.outfit_id,
        accepted=feedback.accepted,
        rating=feedback.rating,
        comfort_rating=feedback.comfort_rating,
        style_rating=feedback.style_rating,
        comment=feedback.comment,
        worn_at=feedback.worn_at,
        worn_with_modifications=feedback.worn_with_modifications,
        modification_notes=feedback.modification_notes,
        actually_worn=feedback.actually_worn,
        wore_instead_items=[UUID(item_id) for item_id in (feedback.wore_instead_items or [])],
        created_at=feedback.created_at,
    )


@router.post("/{outfit_id}/family-rating", response_model=FamilyRatingResponse)
async def submit_family_rating(
    outfit_id: UUID,
    request: FamilyRatingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyRatingResponse:
    result = await db.execute(select(Outfit).where(Outfit.id == outfit_id))
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")

    if outfit.scheduled_for is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "OUTFIT_IS_TEMPLATE",
                "message": "Cannot rate a lookbook template",
            },
        )

    if outfit.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rate your own outfit",
        )

    if not current_user.family_id or not outfit.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "You must be in the same family to rate outfits",
                "error_code": "NOT_IN_FAMILY",
            },
        )

    owner_result = await db.execute(
        select(User).where(User.id == outfit.user_id, User.is_active == True)  # noqa: E712
    )
    owner = owner_result.scalar_one_or_none()
    if not owner or owner.family_id != current_user.family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "You must be in the same family to rate outfits",
                "error_code": "NOT_IN_FAMILY",
            },
        )

    existing = await db.execute(
        select(FamilyOutfitRating).where(
            and_(
                FamilyOutfitRating.outfit_id == outfit_id,
                FamilyOutfitRating.user_id == current_user.id,
            )
        )
    )
    rating = existing.scalar_one_or_none()

    if rating:
        rating.rating = request.rating
        rating.comment = request.comment
    else:
        rating = FamilyOutfitRating(
            outfit_id=outfit_id,
            user_id=current_user.id,
            rating=request.rating,
            comment=request.comment,
        )
        db.add(rating)

    await db.flush()
    await db.refresh(rating)

    return FamilyRatingResponse(
        id=rating.id,
        user_id=rating.user_id,
        user_display_name=current_user.display_name or current_user.email,
        user_avatar_url=current_user.avatar_url,
        rating=rating.rating,
        comment=rating.comment,
        created_at=rating.created_at,
    )


@router.get("/{outfit_id}/family-ratings", response_model=list[FamilyRatingResponse])
async def get_family_ratings(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FamilyRatingResponse]:
    result = await db.execute(select(Outfit).where(Outfit.id == outfit_id))
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")

    if outfit.user_id != current_user.id:
        if not current_user.family_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        owner_result = await db.execute(
            select(User).where(User.id == outfit.user_id, User.is_active == True)  # noqa: E712
        )
        owner = owner_result.scalar_one_or_none()
        if not owner or owner.family_id != current_user.family_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    ratings_result = await db.execute(
        select(FamilyOutfitRating)
        .where(FamilyOutfitRating.outfit_id == outfit_id)
        .options(selectinload(FamilyOutfitRating.user))
        .order_by(FamilyOutfitRating.created_at.desc())
    )
    ratings = list(ratings_result.scalars().all())

    return [
        FamilyRatingResponse(
            id=r.id,
            user_id=r.user_id,
            user_display_name=r.user.display_name or r.user.email,
            user_avatar_url=r.user.avatar_url,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
        )
        for r in ratings
    ]


def _check_studio_kill_switch() -> None:
    if get_settings().studio_disabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "STUDIO_UNAVAILABLE",
                "message": "Studio is temporarily unavailable. AI features still work.",
            },
        )


class StudioCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UUID] = Field(min_length=1, max_length=20)
    occasion: str = Field(max_length=50)
    name: Annotated[str | None, Field(max_length=100)] = None
    scheduled_for: date | None = None
    mark_worn: bool = False
    source_item_id: UUID | None = None

    @field_validator("occasion")
    @classmethod
    def validate_occasion(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_OCCASIONS:
            raise ValueError(
                f"Invalid occasion '{v}'. Must be one of: {', '.join(sorted(VALID_OCCASIONS))}"
            )
        return v


class WoreInsteadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UUID] = Field(min_length=1, max_length=20)
    rating: Annotated[int | None, Field(ge=1, le=5)] = None
    comment: Annotated[str | None, Field(max_length=1000)] = None
    scheduled_for: date | None = None


class CloneToLookbookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)


class WearTodayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_for: date | None = None


class PatchOutfitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(max_length=100)] = None
    items: Annotated[list[UUID] | None, Field(min_length=1, max_length=20)] = None


async def _run_learning_safely(db: AsyncSession, outfit_id: UUID, user_id: UUID) -> None:
    try:
        await LearningService(db).process_feedback(outfit_id, user_id)
    except Exception as e:
        logger.exception("learning process_feedback failed for outfit %s: %s", outfit_id, e)


@router.post("/studio", response_model=OutfitResponse, status_code=status.HTTP_201_CREATED)
async def create_studio_outfit(
    request: StudioCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    _check_studio_kill_switch()
    await rate_limit_by_user(
        str(current_user.id), "studio_create", max_requests=20, window_seconds=60
    )

    service = StudioService(db)
    try:
        outfit = await service.create_from_scratch(
            user=current_user,
            item_ids=request.items,
            occasion=request.occasion,
            name=request.name,
            scheduled_for=request.scheduled_for,
            mark_worn=request.mark_worn,
            source_item_id=request.source_item_id,
        )
    except ItemOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "OUTFIT_ITEM_OWNERSHIP",
                "message": "One or more items do not belong to you",
            },
        ) from None

    await db.commit()
    await _run_learning_safely(db, outfit.id, current_user.id)
    await clear_suggestions(current_user.id, outfit.occasion)

    full = await service.get_full_outfit(outfit.id)
    return outfit_to_response(full)


@router.post("/{outfit_id}/wore-instead", response_model=OutfitResponse)
async def create_wore_instead_outfit(
    outfit_id: UUID,
    request: WoreInsteadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    _check_studio_kill_switch()
    await rate_limit_by_user(
        str(current_user.id), "wore_instead", max_requests=10, window_seconds=60
    )

    service = StudioService(db)
    try:
        replacement = await service.create_wore_instead(
            user=current_user,
            original_outfit_id=outfit_id,
            item_ids=request.items,
            rating=request.rating,
            comment=request.comment,
            scheduled_for=request.scheduled_for,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "OUTFIT_NOT_FOUND", "message": "Outfit not found"},
        ) from None
    except ItemOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "OUTFIT_ITEM_OWNERSHIP",
                "message": "One or more items do not belong to you",
            },
        ) from None

    await db.commit()
    await _run_learning_safely(db, replacement.id, current_user.id)
    await clear_suggestions(current_user.id, replacement.occasion)

    full = await service.get_full_outfit(replacement.id)
    return outfit_to_response(full)


@router.post("/{outfit_id}/clone-to-lookbook", response_model=OutfitResponse)
async def clone_outfit_to_lookbook(
    outfit_id: UUID,
    request: CloneToLookbookRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    _check_studio_kill_switch()
    await rate_limit_by_user(
        str(current_user.id), "clone_to_lookbook", max_requests=20, window_seconds=60
    )

    service = StudioService(db)
    try:
        clone = await service.clone_to_lookbook(
            user=current_user,
            source_outfit_id=outfit_id,
            name=request.name,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "OUTFIT_NOT_FOUND", "message": "Outfit not found"},
        ) from None

    await db.commit()
    await _run_learning_safely(db, clone.id, current_user.id)

    full = await service.get_full_outfit(clone.id)
    return outfit_to_response(full)


@router.post("/{outfit_id}/wear-today", response_model=OutfitResponse)
async def wear_outfit_today(
    outfit_id: UUID,
    request: WearTodayRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    _check_studio_kill_switch()
    await rate_limit_by_user(str(current_user.id), "wear_today", max_requests=10, window_seconds=60)

    service = StudioService(db)
    try:
        wear = await service.wear_today(
            user=current_user,
            template_id=outfit_id,
            scheduled_for=request.scheduled_for,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "OUTFIT_NOT_FOUND", "message": "Outfit not found"},
        ) from None
    except OutfitNotTemplateError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "OUTFIT_NOT_TEMPLATE",
                "message": "wear-today requires a lookbook template",
            },
        ) from None

    await db.commit()
    await _run_learning_safely(db, wear.id, current_user.id)
    await clear_suggestions(current_user.id, wear.occasion)

    full = await service.get_full_outfit(wear.id)
    return outfit_to_response(full)


@router.patch("/{outfit_id}", response_model=OutfitResponse)
async def patch_outfit_endpoint(
    outfit_id: UUID,
    request: PatchOutfitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    _check_studio_kill_switch()
    await rate_limit_by_user(
        str(current_user.id), "patch_outfit", max_requests=30, window_seconds=60
    )

    if request.name is None and request.items is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "PATCH_EMPTY", "message": "No fields provided"},
        )

    service = StudioService(db)
    try:
        updated = await service.patch_outfit(
            user=current_user,
            outfit_id=outfit_id,
            name=request.name,
            items=request.items,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "OUTFIT_NOT_FOUND", "message": "Outfit not found"},
        ) from None
    except ItemOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "OUTFIT_ITEM_OWNERSHIP",
                "message": "One or more items do not belong to you",
            },
        ) from None
    except OutfitWornImmutableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "OUTFIT_WORN_IMMUTABLE",
                "message": "Cannot modify items on a worn outfit. Create a new lookbook entry instead.",
            },
        ) from None

    await db.commit()

    full = await service.get_full_outfit(updated.id)
    return outfit_to_response(full)


@router.delete("/{outfit_id}/family-rating", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_rating(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(
        select(FamilyOutfitRating).where(
            and_(
                FamilyOutfitRating.outfit_id == outfit_id,
                FamilyOutfitRating.user_id == current_user.id,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rating not found",
        )

    await db.delete(rating)
    await db.flush()
