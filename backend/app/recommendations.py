from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import UserProfile
from .nutrislice import get_menu
from .schemas import (
    GoalProgress,
    MenuFood,
    MenuNutrition,
    PlateItem,
    RecommendationRequest,
    RecommendationResponse,
)


MEAL_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.40, "overnight": 0.15}
MEAT_MARKERS = {"beef", "poultry", "chicken", "pork", "fish", "shellfish"}


@dataclass
class CandidatePlate:
    items: list[tuple[MenuFood, float]] = field(default_factory=list)
    nutrition: MenuNutrition = field(default_factory=MenuNutrition)


def _scaled(nutrition: MenuNutrition, servings: float) -> MenuNutrition:
    return MenuNutrition(**{name: getattr(nutrition, name) * servings for name in MenuNutrition.model_fields})


def _add(left: MenuNutrition, right: MenuNutrition) -> MenuNutrition:
    return MenuNutrition(**{name: getattr(left, name) + getattr(right, name) for name in MenuNutrition.model_fields})


def _target(profile: UserProfile, meal: str, override: int | None) -> MenuNutrition:
    weight = MEAL_WEIGHTS.get(meal, 1 / max(profile.meals_per_day, 2))
    calories = float(override if override is not None else round(profile.daily_calorie_goal * weight))
    macro_scale = calories / profile.daily_calorie_goal
    return MenuNutrition(
        calories=calories,
        protein_g=profile.protein_goal_g * macro_scale,
        carbs_g=profile.carb_goal_g * macro_scale,
        fat_g=profile.fat_goal_g * macro_scale,
        fiber_g=profile.fiber_goal_g * macro_scale,
        sodium_mg=profile.sodium_limit_mg * macro_scale,
    )


def _contains_allergen(item: MenuFood, allergies: set[str]) -> bool:
    if allergies.intersection(item.allergens):
        return True
    ingredients = item.ingredients.lower()
    return any(allergy in ingredients for allergy in allergies if len(allergy) > 3)


def _diet_allowed(item: MenuFood, preferences: set[str]) -> bool:
    text = f"{item.name} {item.ingredients}".lower()
    tags = set(item.dietary_tags)
    if "vegan" in preferences and "vegan" not in tags:
        return False
    if "vegetarian" in preferences:
        if "vegan" not in tags and "vegetarian" not in tags and any(word in text for word in MEAT_MARKERS):
            return False
    if "halal" in preferences and any(word in text for word in ("pork", "bacon", "ham")):
        return False
    return True


def _score(plate: CandidatePlate, target: MenuNutrition) -> float:
    total = plate.nutrition
    calorie_error = abs(total.calories - target.calories) / max(target.calories, 1) * 100
    protein_shortfall = max(0, target.protein_g - total.protein_g) / max(target.protein_g, 1) * 35
    fiber_shortfall = max(0, target.fiber_g - total.fiber_g) / max(target.fiber_g, 1) * 10
    fat_error = abs(total.fat_g - target.fat_g) / max(target.fat_g, 1) * 8
    sodium_over = max(0, total.sodium_mg - target.sodium_mg) / max(target.sodium_mg, 1) * 28
    categories = {item.category for item, _ in plate.items}
    variety_penalty = 0
    if "protein" not in categories:
        variety_penalty += 22
    if "vegetable" not in categories:
        variety_penalty += 16
    if len(categories) < min(3, len(plate.items)):
        variety_penalty += 6
    category_counts = {category: sum(item.category == category for item, _ in plate.items) for category in categories}
    variety_penalty += max(0, category_counts.get("protein", 0) - 1) * 7
    variety_penalty += max(0, category_counts.get("other", 0)) * 5
    return calorie_error + protein_shortfall + fiber_shortfall + fat_error + sodium_over + variety_penalty


def _optimize(items: list[MenuFood], target: MenuNutrition) -> CandidatePlate:
    viable = [
        item
        for item in items
        if item.nutrition_complete
        and item.category not in {"condiment", "dessert"}
        and item.serving_unit.lower() not in {"tbsp", "tsp", "teaspoon"}
        and 15 <= item.nutrition.calories <= target.calories * 1.1
    ]
    viable.sort(
        key=lambda item: (
            item.category not in {"protein", "vegetable", "grain"},
            -(item.nutrition.protein_g * 3 + item.nutrition.fiber_g * 2) / max(item.nutrition.calories, 1),
        )
    )
    viable = viable[:18]
    beam = [CandidatePlate()]
    finished: list[CandidatePlate] = []
    for _ in range(4):
        expanded: list[CandidatePlate] = []
        for plate in beam:
            used = {item.id for item, _ in plate.items}
            for item in viable:
                if item.id in used:
                    continue
                category_count = sum(selected.category == item.category for selected, _ in plate.items)
                if category_count >= 2 or (item.category == "other" and category_count >= 1):
                    continue
                for servings in (0.5, 1.0, 1.5, 2.0):
                    total = _add(plate.nutrition, _scaled(item.nutrition, servings))
                    if total.calories > target.calories * 1.28:
                        continue
                    expanded.append(CandidatePlate(items=plate.items + [(item, servings)], nutrition=total))
        if not expanded:
            break
        expanded.sort(key=lambda plate: _score(plate, target))
        beam = expanded[:280]
        finished.extend(beam[:60])
    if not finished:
        return CandidatePlate()
    return min(finished, key=lambda plate: _score(plate, target))


def _portion(item: MenuFood, servings: float) -> str:
    amount = item.serving_amount * servings
    rendered = str(int(amount)) if amount.is_integer() else f"{amount:g}"
    unit = item.serving_unit
    if unit in {"serving", "piece", "slice", "cup"} and amount > 1:
        unit += "s"
    return f"{rendered} {unit}"


def _reason(item: MenuFood) -> str:
    if item.category == "protein":
        return "Anchors the plate with protein"
    if item.category == "vegetable":
        return "Adds fiber and micronutrient variety"
    if item.category == "grain":
        return "Provides steady meal energy"
    return "Rounds out your calorie and macro target"


async def recommend(profile: UserProfile, request: RecommendationRequest) -> RecommendationResponse:
    menu = await get_menu(request.hall_slug, request.at, request.meal)
    if menu.source != "nutrislice":
        from fastapi import HTTPException
        raise HTTPException(503, "The live menu is unavailable for this service. Try again shortly; sample foods will not be used for calorie planning.")
    allergies = {value.lower() for value in profile.allergies}
    preferences = {value.lower() for value in profile.dietary_preferences}
    allergy_safe = [item for item in menu.items if not _contains_allergen(item, allergies)]
    diet_safe = [item for item in allergy_safe if _diet_allowed(item, preferences)]
    target = _target(profile, menu.meal, request.meal_calorie_target)
    excluded = set(request.excluded_item_ids)
    available = [item for item in diet_safe if item.id not in excluded]
    result = _optimize(available, target)
    plate = [
        PlateItem(
            **item.model_dump(), servings=servings, portion_label=_portion(item, servings),
            line_nutrition=_scaled(item.nutrition, servings), why=_reason(item),
        )
        for item, servings in result.items
    ]
    match = max(0, min(100, round(100 - abs(result.nutrition.calories - target.calories) / max(target.calories, 1) * 100)))
    return RecommendationResponse(
        hall=menu.hall,
        date=menu.date,
        meal=menu.meal,
        target_calories=round(target.calories),
        plate=plate,
        progress=GoalProgress(target=target, total=result.nutrition, calorie_match_percent=match),
        excluded_for_allergies=len(menu.items) - len(allergy_safe),
        excluded_for_diet=len(allergy_safe) - len(diet_safe),
        data_source=menu.source,
        generated_at=datetime.now().astimezone(),
        safety_message="Items matching your saved allergens were excluded. Recipes and cross-contact can change—confirm labels and ask dining staff before eating.",
        note=(menu.note if not excluded else " ".join(filter(None, [menu.note, "Rebuilt without the foods you marked unavailable. Portions may change to stay near your target; confirm availability at the station."]))) if plate else ("Your logged calories have reached your saved daily goal. No calorie-targeted plate is suggested; you can still log foods you eat. Your needs may vary." if target.calories == 0 else "No nutritionally complete alternatives remain for this service and your saved requirements. Try another hall; dietary filters have not been relaxed."),
    )
