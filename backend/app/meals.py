"""Explicit, account-owned consumption records; recommendations are never logged automatically."""
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_account
from .database import get_session
from .models import Account, MealLog
from .nutrislice import hall_details
from .nutrislice import get_menu
from . import planning
from .recommendations import _portion

router = APIRouter(prefix="/api/meals", tags=["Meal history"])
EASTERN = ZoneInfo("America/New_York")


class EatenItem(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    portion_label: str = Field(min_length=1, max_length=100)
    # User-confirmed estimates are snapshots: menu changes must not alter history.
    calories: float = Field(ge=0, le=10000, allow_inf_nan=False)


class MealCreate(BaseModel):
    id: UUID
    consumed_at: datetime
    hall_slug: str = Field(max_length=80)
    meal: str = Field(min_length=1, max_length=32)
    items: list[EatenItem] = Field(min_length=1, max_length=20)

    @field_validator("consumed_at")
    @classmethod
    def valid_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include a time zone for the meal.")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Meals cannot be logged in the future.")
        return value


class MealRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    consumed_at: datetime
    hall_slug: str
    hall_name: str
    meal: str
    items: list[EatenItem]
    calories: float
    voided: bool


class MenuSelection(BaseModel):
    food_id: str = Field(min_length=1, max_length=200)
    servings: float = Field(ge=0.25, le=6, allow_inf_nan=False)


class MenuMealCreate(BaseModel):
    id: UUID
    hall_slug: str = Field(max_length=80)
    menu_date: date
    meal: str = Field(max_length=32)
    items: list[MenuSelection] = Field(min_length=1, max_length=20)


@router.get("/menu")
async def search_menu(hall_slug: str, q: str = Query(default="", max_length=100), account: Account = Depends(current_account)):
    at = planning.now()
    hall = planning.open_hall(hall_slug, at)
    menu = await get_menu(hall_slug, at)
    if menu.source != "nutrislice":
        raise HTTPException(503, "No live menu is available for this service. Please try again later.")
    terms = q.casefold().split()
    matches = [item for item in menu.items if all(term in f"{item.name} {item.station}".casefold() for term in terms)]
    return {"hall": hall, "date": menu.date, "meal": menu.meal, "items": matches[:40], "match_count": len(matches),
            "note": "Published menu for this service, not a real-time stock guarantee. Confirm portions, ingredients, and availability with dining staff."}


@router.post("/from-menu", response_model=MealRecord)
async def log_menu_meal(payload: MenuMealCreate, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    existing = await db.get(MealLog, (account.id, str(payload.id)))
    if existing:
        return existing
    at = planning.now()
    planning.open_hall(payload.hall_slug, at)
    menu = await get_menu(payload.hall_slug, at)
    if menu.source != "nutrislice":
        raise HTTPException(503, "The live menu is unavailable. Your food has not been logged.")
    if payload.menu_date != menu.date or payload.meal != menu.meal:
        raise HTTPException(409, "The dining service has changed. Search the current menu again before logging.")
    foods = {item.id: item for item in menu.items}
    items = []
    if len({item.food_id for item in payload.items}) != len(payload.items):
        raise HTTPException(422, "Select each food once and adjust its servings.")
    for selection in payload.items:
        food = foods.get(selection.food_id)
        if not food or not food.nutrition_complete:
            raise HTTPException(409, "A selected food is no longer listed or has incomplete nutrition. Search again.")
        items.append(EatenItem(id=food.id, name=food.name, portion_label=_portion(food, selection.servings),
                               calories=round(food.nutrition.calories * selection.servings, 2)))
    return await log_meal(MealCreate(id=payload.id, consumed_at=at, hall_slug=payload.hall_slug, meal=menu.meal, items=items), account, db)


@router.post("", response_model=MealRecord)
async def log_meal(payload: MealCreate, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    key = (account.id, str(payload.id))
    existing = await db.get(MealLog, key)
    if existing:
        return existing  # Idempotent retries cannot double-count a meal.
    try:
        hall = hall_details(payload.hall_slug)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, "Unknown dining hall.") from exc
    total = round(sum(item.calories for item in payload.items), 2)
    if total > 10000:
        raise HTTPException(422, "Meal calories exceed the supported range.")
    record = MealLog(account_id=account.id, id=str(payload.id), consumed_at=payload.consumed_at.astimezone(timezone.utc),
                     hall_slug=hall.slug, hall_name=hall.short_name, meal=payload.meal,
                     items=[item.model_dump() for item in payload.items], calories=total)
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.get(MealLog, key)
        if existing:
            return existing
        raise
    await db.refresh(record)
    return record


@router.get("")
async def history(start: date = Query(), account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    if start.year < 1900 or start > date(9999, 12, 24):
        raise HTTPException(422, "Choose a valid week start date.")
    # Construct each local boundary independently for 23/25-hour DST days.
    begin = datetime.combine(start, time.min, EASTERN)
    end = datetime.combine(start + timedelta(days=7), time.min, EASTERN)
    rows = (await db.scalars(select(MealLog).where(
        MealLog.account_id == account.id, MealLog.voided.is_(False),
        MealLog.consumed_at >= begin.astimezone(timezone.utc),
        MealLog.consumed_at < end.astimezone(timezone.utc),
    ).order_by(MealLog.consumed_at.desc()))).all()
    days = {str(start + timedelta(days=i)): 0.0 for i in range(7)}
    records = []
    for row in rows:
        stamp = row.consumed_at
        if stamp.tzinfo is None:  # SQLite test adapter; PostgreSQL returns aware timestamps.
            stamp = stamp.replace(tzinfo=timezone.utc)
        days[str(stamp.astimezone(EASTERN).date())] += row.calories
        records.append(MealRecord.model_validate(row).model_copy(update={"consumed_at": stamp}))
    return {"timezone": "America/New_York", "start": start,
            "days": [{"date": day, "calories": round(value, 2)} for day, value in days.items()],
            "total_calories": round(sum(days.values()), 2), "meals": records}


@router.delete("/{meal_id}", status_code=204)
async def remove_meal(meal_id: UUID, account: Account = Depends(current_account), db: AsyncSession = Depends(get_session)):
    row = await db.get(MealLog, (account.id, str(meal_id)))
    if not row:
        raise HTTPException(404, "Meal not found.")
    row.voided = True  # Keep the idempotency key even after undoing a log.
    await db.commit()
    return Response(status_code=204)
