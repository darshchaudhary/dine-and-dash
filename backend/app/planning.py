from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from .models import MealLog
from .nutrislice import EASTERN, hall_details


def now():
    return datetime.now(EASTERN)


def open_hall(slug, at):
    try:
        hall = hall_details(slug, at)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not hall.open_now:
        raise HTTPException(409, f"{hall.short_name} is closed. Plate building and current-menu search are unavailable. Hours: {hall.hours}.")
    return hall


async def consumed_today(db, account_id, at):
    day = at.astimezone(EASTERN).date()
    start = datetime.combine(day, time.min, EASTERN).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, EASTERN).astimezone(timezone.utc)
    return float(await db.scalar(select(func.coalesce(func.sum(MealLog.calories), 0)).where(
        MealLog.account_id == account_id, MealLog.voided.is_(False),
        MealLog.consumed_at >= start, MealLog.consumed_at < end,
    )))


def remaining_target(daily_goal, consumed, meal, planned_meals=None):
    remaining = max(0, daily_goal - consumed)
    # Reserve a share for later services; snack/extra-food log rows do not count
    # as entire meals. These are planning weights, not a change to saved goals.
    weights = {"breakfast": (0.25, 1.0), "lunch": (0.35, 0.75), "dinner": (0.4, 0.4), "overnight": (1, 1)}
    weight, remaining_weight = weights.get(meal, (1, 1))
    if planned_meals:
        order = ["breakfast", "lunch", "dinner", "overnight"]
        later = [name for name in planned_meals if order.index(name) > order.index(meal)]
        remaining_weight = weight + sum(weights[name][0] for name in later)
    return min(2500, max(1, round(remaining * weight / remaining_weight))) if remaining > 0 else 0
