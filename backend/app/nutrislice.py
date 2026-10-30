from __future__ import annotations

import math
import re
import time
from datetime import date, datetime, time as clock_time
from zoneinfo import ZoneInfo

import httpx

from .config import get_settings
from .schemas import DiningHall, MenuFood, MenuNutrition, MenuResponse


EASTERN = ZoneInfo("America/New_York")

# Regular hours: https://dining.gatech.edu/dining-locations/hours-operation
# Verified 2026-10-24; holiday and break schedules may differ.
HALLS: dict[str, dict] = {
    "brittain": {
        "id": 40536,
        "name": "Brittain Dining Hall",
        "short_name": "Brittain",
        "hours": "Mon–Fri · 11 AM–11 PM · Weekends closed",
        "weekdays": {0, 1, 2, 3, 4},
        "open": (clock_time(11), clock_time(23)),
        "meals": ["lunch", "dinner"],
    },
    "north-ave-dining-hall": {
        "id": 40132,
        "name": "North Ave Dining Hall",
        "short_name": "North Ave",
        "hours": "Mon–Fri 7 AM–11 PM · Weekends 9 AM–9 PM",
        "weekdays": set(range(7)),
        "open": (clock_time(7), clock_time(23)),
        "weekend_open": (clock_time(9), clock_time(21)),
        "meals": ["breakfast", "lunch", "dinner", "overnight"],
    },
    "west-village": {
        "id": 40126,
        "name": "West Village",
        "short_name": "West Village",
        "hours": "Mon–Fri 7 AM–11 PM · Weekends 9 AM–9 PM",
        "weekdays": set(range(7)),
        "open": (clock_time(7), clock_time(23)),
        "weekend_open": (clock_time(9), clock_time(21)),
        "meals": ["breakfast", "lunch", "dinner"],
    },
}

MENU_TYPE_IDS = {"breakfast": 8736, "lunch": 8737, "dinner": 8738, "overnight": 28855}

ALLERGEN_ALIASES = {
    "egg": "eggs",
    "eggs": "eggs",
    "milk": "milk",
    "dairy": "milk",
    "peanut": "peanuts",
    "peanuts": "peanuts",
    "tree-nut": "tree nuts",
    "tree-nuts": "tree nuts",
    "tree nuts": "tree nuts",
    "wheat": "wheat",
    "soy": "soy",
    "fish": "fish",
    "shellfish": "shellfish",
    "sesame": "sesame",
    "containing-gluten": "gluten",
    "gluten": "gluten",
}

_cache: dict[str, tuple[float, MenuResponse]] = {}


def meal_for_time(value: datetime, hall_slug: str) -> str:
    local = value.astimezone(EASTERN) if value.tzinfo else value.replace(tzinfo=EASTERN)
    hour = local.hour + local.minute / 60
    if hour < 11:
        return "breakfast"
    if hour < 17:
        return "lunch"
    if hour < 23 or hall_slug != "north-ave-dining-hall":
        return "dinner"
    return "overnight"


def hall_details(slug: str, at: datetime | None = None) -> DiningHall:
    if slug not in HALLS:
        raise ValueError(f"Unknown dining hall: {slug}")
    value = at or datetime.now(EASTERN)
    local = value.astimezone(EASTERN) if value.tzinfo else value.replace(tzinfo=EASTERN)
    data = HALLS[slug]
    if local.weekday() not in data["weekdays"]:
        open_now = False
    else:
        window = data.get("weekend_open") if local.weekday() >= 5 else data["open"]
        start, end = window or data["open"]
        open_now = start <= local.time().replace(tzinfo=None) < end
    return DiningHall(
        id=data["id"],
        slug=slug,
        name=data["name"],
        short_name=data["short_name"],
        hours=data["hours"],
        open_now=open_now,
        available_meals=data["meals"],
    )


def all_halls(at: datetime | None = None) -> list[DiningHall]:
    return [hall_details(slug, at) for slug in HALLS]


def classify_food(name: str, station: str) -> str:
    # A station describes location, not every food's nutritional role.
    text = name.casefold()
    if any(word in text for word in ("doughnut", "donut", "cookie", "cupcake", "cake", "brownie", "ice cream", "dessert", "muffin")):
        return "dessert"
    if any(word in text for word in ("oregano", "crushed red pepper", "olive oil", "mayonnaise", "mayo", "mustard", "dressing", "salsa", "ketchup", "seasoning", "vinegar", "sauce", "marinara", "grated parmesan")):
        return "condiment"
    if any(word in text for word in ("green bean", "collard", "broccoli", "cauliflower", "spinach", "carrot", "vegetable", "veggie", "zucchini", "squash", "kale", "mushroom", "cucumber", "tomato", "lettuce", "romaine", "arcadian", "cabbage", "onion", "jalapeno", "banana pepper")):
        # Mixed starch-based dishes still cover their own roles below.
        if not any(word in text for word in ("pizza", "pasta", "rice", "noodle", "tortilla")):
            return "vegetable"
    if any(word in text for word in ("pizza", "rice", "quinoa", "potato", "fries", "pasta", "ravioli", "spaghetti", "noodle", "bread", "bun", "roll", "tortilla", "oat", "cereal", "grits")):
        return "grain"
    if any(re.search(r"\b" + word + r"\b", text) for word in ("chicken", "turkey", "beef", "pork", "fish", "tofu", "egg", "eggs", "bean", "beans", "lentil", "chickpea", "burger", "ham", "salami", "steak", "bratwurst", "bacon", "shrimp", "falafel", "pepperoni", "shawarma")):
        return "protein"
    if any(word in text for word in ("fruit", "apple", "orange", "banana", "berry", "melon")):
        return "fruit"
    if "pepper" in text and "cheese" not in text:
        return "vegetable"
    if "salad" in text or "soup" in text:
        return "vegetable"
    return "other"


def _safe_float(value: object) -> float:
    try:
        result = float(value or 0)
        return result if math.isfinite(result) and result >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _parse_food(raw: dict, station: str) -> MenuFood | None:
    food = raw.get("food")
    if not food or not food.get("name"):
        return None
    rounded = food.get("rounded_nutrition_info") or {}
    keys = {"calories": "calories", "protein_g": "g_protein", "carbs_g": "g_carbs", "fat_g": "g_fat", "fiber_g": "g_fiber", "sodium_mg": "mg_sodium"}
    missing = []
    values = {}
    for key, upstream in keys.items():
        raw_value = rounded.get(upstream)
        try:
            value = float(raw_value)
            if isinstance(raw_value, bool) or not math.isfinite(value) or not 0 <= value <= 100000:
                raise ValueError("Invalid nutrition value")
        except (TypeError, ValueError):
            missing.append(key)
            value = 0
        values[key] = value
    nutrition = MenuNutrition(**values)
    allergens: set[str] = set()
    dietary: set[str] = set()
    for icon in (food.get("icons") or {}).get("food_icons", []):
        slug = str(icon.get("slug") or "").lower()
        name = str(icon.get("name") or slug).lower()
        if icon.get("behavior") == 1:
            canonical = ALLERGEN_ALIASES.get(slug) or ALLERGEN_ALIASES.get(name)
            if canonical:
                allergens.add(canonical)
        elif icon.get("behavior") == 2:
            dietary.add(slug or name)
    serving = food.get("serving_size_info") or {}
    amount = _safe_float(serving.get("serving_size_amount")) or 1
    ingredients = str(food.get("ingredients") or "")
    # Reject extreme batch records that cannot describe a practical serving.
    plausible = nutrition.calories <= 2000 and not ("bread" in food["name"].casefold() and "slice" in str(serving.get("serving_size_unit", "")).casefold() and nutrition.calories > 400)
    complete = plausible and not set(missing).intersection({"calories", "protein_g", "carbs_g", "fat_g"}) and nutrition.calories > 0 and any(
        value > 0 for value in (nutrition.protein_g, nutrition.carbs_g, nutrition.fat_g)
    )
    return MenuFood(
        id=str(food.get("id") or raw.get("id")),
        name=re.sub(r"\s+", " ", food["name"]).strip(),
        station=station or "Dining hall station",
        category=classify_food(food["name"], station),
        serving_amount=amount,
        serving_unit=str(serving.get("serving_size_unit") or raw.get("serving_size_unit") or "serving"),
        nutrition=nutrition,
        allergens=sorted(allergens),
        dietary_tags=sorted(dietary),
        ingredients=ingredients,
        nutrition_complete=complete,
        missing_nutrients=missing,
    )


def _parse_response(payload: dict, slug: str, target_date: date, meal: str) -> MenuResponse:
    day = next((d for d in payload.get("days", []) if d.get("date") == target_date.isoformat()), {})
    station = "Dining hall station"
    items: list[MenuFood] = []
    seen: set[str] = set()
    for raw in day.get("menu_items", []):
        if raw.get("is_station_header"):
            station = str(raw.get("text") or raw.get("category") or station)
            continue
        item = _parse_food(raw, station)
        if item and item.id not in seen:
            items.append(item)
            seen.add(item.id)
    incomplete = sum(not item.nutrition_complete for item in items)
    return MenuResponse(
        hall=hall_details(slug),
        date=target_date,
        meal=meal,
        items=items,
        unavailable_nutrition_count=incomplete,
        source="nutrislice",
        fetched_at=datetime.now(EASTERN),
        note=(
            f"{incomplete} menu item{'s' if incomplete != 1 else ''} had incomplete nutrition and will not be used in recommendations."
            if incomplete
            else None
        ),
    )


def _demo_items() -> list[MenuFood]:
    data = [
        ("demo-chicken", "Herb Grilled Chicken", "Mindful Kitchen", "protein", 1, "breast", 230, 38, 2, 7, 0, 390, [], ["gluten-friendly"]),
        ("demo-tofu", "Ginger Sesame Tofu", "Plant Forward", "protein", 4, "oz", 190, 18, 10, 9, 3, 360, ["soy", "sesame"], ["vegan"]),
        ("demo-quinoa", "Lemon Herb Quinoa", "Harvest Table", "grain", 0.5, "cup", 145, 5, 26, 3, 3, 135, [], ["vegan", "gluten-friendly"]),
        ("demo-rice", "Brown Rice", "Global Kitchen", "grain", 0.5, "cup", 110, 3, 23, 1, 2, 10, [], ["vegan", "gluten-friendly"]),
        ("demo-broccoli", "Roasted Broccoli", "Harvest Table", "vegetable", 0.5, "cup", 65, 4, 9, 2, 4, 115, [], ["vegan", "gluten-friendly"]),
        ("demo-sweet-potato", "Roasted Sweet Potato", "Harvest Table", "vegetable", 0.5, "cup", 120, 2, 27, 1, 4, 170, [], ["vegan", "gluten-friendly"]),
        ("demo-salad", "Garden Greens", "Salad Bar", "vegetable", 2, "cups", 45, 3, 8, 1, 3, 65, [], ["vegan", "gluten-friendly"]),
        ("demo-yogurt", "Greek Yogurt", "Daily Market", "other", 0.75, "cup", 130, 15, 9, 4, 0, 70, ["milk"], ["vegetarian"]),
    ]
    return [
        MenuFood(
            id=row[0], name=row[1], station=row[2], category=row[3], serving_amount=row[4],
            serving_unit=row[5], nutrition=MenuNutrition(calories=row[6], protein_g=row[7], carbs_g=row[8],
            fat_g=row[9], fiber_g=row[10], sodium_mg=row[11]), allergens=row[12], dietary_tags=row[13],
            ingredients="Demo nutrition record", nutrition_complete=True,
        )
        for row in data
    ]


async def get_menu(slug: str, at: datetime | None = None, meal: str | None = None) -> MenuResponse:
    if slug not in HALLS:
        raise ValueError(f"Unknown dining hall: {slug}")
    value = at or datetime.now(EASTERN)
    local = value.astimezone(EASTERN) if value.tzinfo else value.replace(tzinfo=EASTERN)
    selected_meal = (meal or meal_for_time(local, slug)).lower()
    if selected_meal not in HALLS[slug]["meals"]:
        selected_meal = HALLS[slug]["meals"][0]
    key = f"{slug}:{local.date()}:{selected_meal}"
    settings = get_settings()
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < settings.menu_cache_seconds:
        return cached[1]
    hall_id = HALLS[slug]["id"]
    menu_id = MENU_TYPE_IDS[selected_meal]
    url = f"{settings.nutrislice_base_url}/menu/api/weeks/school/{hall_id}/menu-type/{menu_id}/{local:%Y/%m/%d}/"
    try:
        async with httpx.AsyncClient(timeout=settings.nutrislice_timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
        result = _parse_response(response.json(), slug, local.date(), selected_meal)
        if not result.items:
            raise ValueError("No published items for this service")
    except (httpx.HTTPError, ValueError, KeyError):
        result = MenuResponse(
            hall=hall_details(slug, local), date=local.date(), meal=selected_meal,
            items=_demo_items(), source="demo", fetched_at=datetime.now(EASTERN),
            note="Live Nutrislice items are unavailable for this service. Showing labeled demo data so you can preview the planner.",
        )
    _cache[key] = (time.monotonic(), result)
    return result
