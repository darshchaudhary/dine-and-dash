from types import SimpleNamespace
from datetime import datetime, timezone
import pytest

from app.nutrislice import _demo_items, classify_food, hall_details, meal_for_time
from app.recommendations import _contains_allergen, _optimize, _target
from app.recommendations import recommend
from app.schemas import MenuResponse, RecommendationRequest


def test_classifies_common_foods():
    assert classify_food("Grilled Chicken", "Grill") == "protein"
    assert classify_food("Roasted Broccoli", "Harvest") == "vegetable"
    assert classify_food("Brown Rice", "Global") == "grain"
    assert classify_food("Hamburger Bun", "Grill") == "grain"
    assert classify_food("Oregano", "Pasta") == "condiment"


def test_allergen_filter_checks_icons_and_ingredients():
    tofu = next(item for item in _demo_items() if item.id == "demo-tofu")
    assert _contains_allergen(tofu, {"soy"})
    assert not _contains_allergen(tofu, {"milk"})


def test_optimizer_builds_balanced_plate_near_target():
    target = SimpleNamespace(
        daily_calorie_goal=2200,
        protein_goal_g=130,
        carb_goal_g=250,
        fat_goal_g=70,
        fiber_goal_g=30,
        sodium_limit_mg=2300,
        meals_per_day=3,
    )
    meal_target = _target(target, "lunch", None)
    result = _optimize(_demo_items(), meal_target)
    categories = {item.category for item, _ in result.items}
    assert result.items
    assert "protein" in categories
    assert "vegetable" in categories
    assert abs(result.nutrition.calories - meal_target.calories) < 180


def test_hall_hours_and_meal_selection():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    noon = datetime(2026, 9, 1, 12, tzinfo=eastern)
    assert meal_for_time(noon, "north-ave-dining-hall") == "lunch"
    assert hall_details("north-ave-dining-hall", noon).open_now


@pytest.mark.asyncio
async def test_alternatives_exclude_unavailable_and_keep_filters(monkeypatch):
    async def menu(*args):
        return MenuResponse(hall=hall_details("north-ave-dining-hall"), date="2026-09-14", meal="lunch",
                            items=_demo_items(), source="nutrislice", fetched_at=datetime.now(timezone.utc))
    monkeypatch.setattr("app.recommendations.get_menu", menu)
    profile = SimpleNamespace(daily_calorie_goal=2200, protein_goal_g=130, carb_goal_g=250,
                              fat_goal_g=70, fiber_goal_g=30, sodium_limit_mg=2300,
                              meals_per_day=3, allergies=["soy"], dietary_preferences=["vegan"])
    request = RecommendationRequest(user_id="test", hall_slug="north-ave-dining-hall", meal_calorie_target=650)
    original = await recommend(profile, request)
    assert original.plate
    unavailable = original.plate[0].id
    result = await recommend(profile, request.model_copy(update={"excluded_item_ids": [unavailable]}))
    assert result.target_calories == 650
    assert all(item.id != unavailable and "soy" not in item.allergens and "vegan" in item.dietary_tags for item in result.plate)
    assert result.plate
    assert abs(result.progress.total.calories - 650) < 200
    assert round(sum(item.line_nutrition.calories for item in result.plate), 2) == round(result.progress.total.calories, 2)
    empty = await recommend(profile, request.model_copy(update={"excluded_item_ids": [item.id for item in _demo_items()]}))
    assert not empty.plate
    assert "not been relaxed" in empty.note
