from __future__ import annotations

import asyncio
from functools import partial
import re
from datetime import datetime

from .models import UserProfile
from .optimizer import CandidatePlate, optimize, portion_options, roles, score
from .planner import PlanningContext
from .preferences import predict_affinities
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
_SOLVERS = asyncio.Semaphore(4)


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
    aliases = {"milk": ("milk", "whey", "casein", "butter", "cheese"), "eggs": ("egg", "eggs"), "soy": ("soy", "soya", "tofu"), "peanuts": ("peanut", "peanuts"), "tree nuts": ("almond", "walnut", "cashew", "pecan", "pistachio"), "gluten": ("wheat", "barley", "rye") }
    return any(re.search(r"\b" + re.escape(word) + r"\b", ingredients) for allergy in allergies for word in aliases.get(allergy, (allergy,)))


def _diet_allowed(item: MenuFood, preferences: set[str]) -> bool:
    text = f"{item.name} {item.ingredients}".lower()
    tags = set(item.dietary_tags)
    if "vegan" in preferences and "vegan" not in tags:
        return False
    if "vegetarian" in preferences and not tags.intersection({"vegan", "vegetarian"}):
        return False
    if "halal" in preferences:
        if "halal" not in tags or re.search(r"\b(pork|bacon|ham)\b", text):
            return False
    return True


def _score(plate: CandidatePlate, target: MenuNutrition) -> float:
    return score(plate.items, target)


def _optimize(items: list[MenuFood], target: MenuNutrition) -> CandidatePlate:
    return optimize(items, target)


def _portion(item: MenuFood, servings: float) -> str:
    amount = round(item.serving_amount * servings, 4)
    if item.serving_unit.casefold().rstrip("s") in {"lb", "pound"}:
        return f"{amount * 16:g} oz"
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


async def recommend(profile: UserProfile, request: RecommendationRequest, context: PlanningContext | None = None) -> RecommendationResponse:
    menu = await get_menu(request.hall_slug, request.at, request.meal)
    if menu.source != "nutrislice":
        from fastapi import HTTPException
        raise HTTPException(503, "The live menu is unavailable for this service. Try again shortly; sample foods will not be used for calorie planning.")
    allergies = {value.lower() for value in profile.allergies}
    preferences = {value.lower() for value in profile.dietary_preferences}
    allergy_safe = [item for item in menu.items if not _contains_allergen(item, allergies)]
    diet_safe = [item for item in allergy_safe if _diet_allowed(item, preferences)]
    target = _target(profile, menu.meal, request.meal_calorie_target)
    context = context or PlanningContext()
    remaining_calories = max(0, profile.daily_calorie_goal - context.consumed.calories)
    share = min(1, target.calories / max(remaining_calories, 1))
    for key, goal in (("protein_g", profile.protein_goal_g), ("carbs_g", profile.carb_goal_g), ("fat_g", profile.fat_goal_g), ("fiber_g", profile.fiber_goal_g), ("sodium_mg", profile.sodium_limit_mg)):
        if key in context.known_nutrients:
            setattr(target, key, max(0, goal - getattr(context.consumed, key)) * share)
    excluded = set(request.excluded_item_ids)
    available = [item for item in diet_safe if item.id not in excluded]
    if len({lock.food_id for lock in request.locked_items}) != len(request.locked_items):
        from fastapi import HTTPException
        raise HTTPException(422, "Keep each food once.")
    async with _SOLVERS:
        result = await asyncio.to_thread(partial(optimize, available, target,
            options=context.options, ratings=context.ratings, recent=context.recent,
            affinities=predict_affinities(available, context.examples),
            locked_items={lock.food_id: lock.servings for lock in request.locked_items},
            previous=request.previous_item_ids, meal=menu.meal))
    if result.status == "invalid_lock":
        from fastapi import HTTPException
        raise HTTPException(409, "A kept food or portion is no longer eligible. Release it and try again.")
    if request.previous_item_ids and not result.items and target.calories > 0:
        from fastapi import HTTPException
        raise HTTPException(409, "No different plate fits the current menu and kept foods. Release a kept food or choose another hall; dietary filters have not been relaxed.")
    plate = [
        PlateItem(
            **item.model_copy(update={"portion_options": portion_options(item), "roles": sorted(roles(item))}).model_dump(), servings=servings, portion_label=_portion(item, servings),
            line_nutrition=_scaled(item.nutrition, servings), why=_reason(item),
        )
        for item, servings in result.items
    ]
    match = max(0, min(100, round(100 - abs(result.nutrition.calories - target.calories) / max(target.calories, 1) * 100)))
    return RecommendationResponse(
        optimizer=result.optimizer, solver_status=result.status, solve_ms=result.solve_ms,
        template=result.template,
        # Sensitivity scenario, not a calibrated confidence interval.
        estimated_calorie_range=(round(result.nutrition.calories * 0.9), round(result.nutrition.calories * 1.1)) if plate else None,
        explanation=[
            f"{result.template}; {len({food.station for food, _ in result.items})} station(s).",
            f"{round(abs(result.nutrition.calories - target.calories))} kcal from your meal target; practical serving increments.",
            "Calorie range illustrates portions 10% smaller or larger; it is not a measured confidence interval.",
        ] + (["Your saved food feedback also adjusts the ranking of similar foods."] if context.examples else [])
          + (["Some fiber or sodium values are missing; shown totals are incomplete."] if any(food.missing_nutrients for food, _ in result.items) else [])
          + (["Earlier meals lack complete nutrient records; affected macro targets use your saved daily proportions."] if len(context.known_nutrients) < len(MenuNutrition.model_fields) else []),
        feedback={item.id: context.ratings.get(item.id, 0) for item, _ in result.items},
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
