"""Account-owned planning preferences and consumption context."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_account
from .database import get_session
from .models import Account, FoodPreference, MealLog, PlannerSettings
from .nutrislice import EASTERN, get_menu
from .schemas import FoodFeedback, MenuNutrition, PlannerOptions
from . import planning

router = APIRouter(prefix="/api/planner", tags=["Plate preferences"])


@dataclass
class PlanningContext:
    options: PlannerOptions = field(default_factory=PlannerOptions)
    ratings: dict[str, int] = field(default_factory=dict)
    recent: dict[str, int] = field(default_factory=dict)
    examples: list[tuple[str, int]] = field(default_factory=list)
    consumed: MenuNutrition = field(default_factory=MenuNutrition)
    known_nutrients: set[str] = field(default_factory=lambda: set(MenuNutrition.model_fields))


@router.get("", response_model=PlannerOptions)
async def get_options(account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    row = await db.get(PlannerSettings, account.id)
    return PlannerOptions.model_validate(row.settings if row else {})


@router.put("", response_model=PlannerOptions)
async def save_options(payload: PlannerOptions, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    row = await db.get(PlannerSettings, account.id)
    if row is None:
        db.add(PlannerSettings(account_id=account.id, settings=payload.model_dump()))
    else:
        row.settings = payload.model_dump()
    await db.commit()
    return payload


@router.put("/feedback")
async def save_feedback(payload: FoodFeedback, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    at = planning.now()
    planning.open_hall(payload.hall_slug, at)
    menu = await get_menu(payload.hall_slug, at)
    if menu.source != "nutrislice":
        raise HTTPException(503, "Could not verify this food. Your preference was not saved.")
    food = next((food for food in menu.items if food.id == payload.food_id), None)
    if food is None:
        raise HTTPException(409, "This food is no longer on the current menu. Refresh before saving feedback.")
    row = await db.get(FoodPreference, (account.id, food.id))
    if row is None:
        db.add(FoodPreference(account_id=account.id, food_id=food.id, name=food.name, rating=payload.rating))
    else:
        row.rating = payload.rating
    await db.commit()
    return {"food_id": food.id, "rating": payload.rating}


@router.get("/feedback")
async def get_feedback(account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(select(FoodPreference).where(FoodPreference.account_id == account.id, FoodPreference.rating != 0).order_by(FoodPreference.name))).all()
    return [{"food_id": row.food_id, "name": row.name, "rating": row.rating} for row in rows]


@router.delete("/feedback/{food_id}")
async def clear_feedback(food_id: str, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    row = await db.get(FoodPreference, (account.id, food_id))
    if row:
        await db.delete(row)
        await db.commit()
    return {"food_id": food_id, "rating": 0}


async def context_for(db: AsyncSession, account_id: str, at: datetime) -> PlanningContext:
    row = await db.get(PlannerSettings, account_id)
    context = PlanningContext(options=PlannerOptions.model_validate(row.settings if row else {}))
    ratings = (await db.scalars(select(FoodPreference).where(FoodPreference.account_id == account_id))).all()
    context.ratings = {row.food_id: row.rating for row in ratings}
    context.examples = [(row.name, row.rating) for row in ratings if row.rating]
    local = at.astimezone(EASTERN)
    start = datetime.combine(local.date(), time.min, EASTERN).astimezone(timezone.utc)
    end = datetime.combine(local.date() + timedelta(days=1), time.min, EASTERN).astimezone(timezone.utc)
    rows = (await db.scalars(select(MealLog).where(MealLog.account_id == account_id, MealLog.voided.is_(False),
                                                 MealLog.consumed_at >= start - timedelta(days=7), MealLog.consumed_at < end))).all()
    counts = Counter()
    nutrients = {key: 0.0 for key in MenuNutrition.model_fields}
    for record in rows:
        counts.update({item["id"] for item in record.items})
        stamp = record.consumed_at if record.consumed_at.tzinfo else record.consumed_at.replace(tzinfo=timezone.utc)
        if stamp < start:
            continue
        nutrients["calories"] += record.calories
        for item in record.items:
            nutrition = item.get("nutrition") or {}
            missing = set(item.get("missing_nutrients") or [])
            for key in MenuNutrition.model_fields:
                if key == "calories":
                    continue
                if key not in nutrition or key in missing:
                    context.known_nutrients.discard(key)
                else:
                    nutrients[key] += nutrition[key]
    context.consumed = MenuNutrition(**nutrients)
    context.recent = dict(counts)
    return context
