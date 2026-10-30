from itertools import product

import pytest

from app import optimizer
from app.nutrislice import _demo_items, _parse_food
from app.optimizer import optimize, portion_options, roles, total_for
from app.schemas import MenuFood, MenuNutrition, PlannerOptions


def food(id, calories=200, protein=15, carbs=25, fat=5, category="protein", **kwargs):
    return MenuFood(id=id, name=kwargs.pop("name", id), station=kwargs.pop("station", "Kitchen"), category=category,
                    nutrition=MenuNutrition(calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, fiber_g=2, sodium_mg=100), **kwargs)


def target(calories=650, **kwargs):
    return MenuNutrition(calories=calories, protein_g=kwargs.get("protein", 40), carbs_g=kwargs.get("carbs", 80), fat_g=15, fiber_g=8, sodium_mg=800)


def test_full_serving_above_target_can_fit_as_half_portion():
    result = optimize([food("pasta", calories=1000, category="grain", name="Chicken pasta")], target(500))
    assert result.items[0][1] == 0.5
    assert result.nutrition.calories == 500
    assert result.template == "Entrée with sides"


def test_counted_and_packaged_foods_have_practical_portions():
    assert portion_options(food("chicken", serving_unit="breast")) == [1, 2]
    assert portion_options(food("yogurt", serving_unit="container")) == [1, 2]
    assert portion_options(food("eggs", serving_unit="pieces", serving_amount=2)) == [0.5, 1, 1.5, 2]
    assert portion_options(food("rice", serving_unit="cup")) == [0.5, 1, 1.5, 2]
    assert "protein" in roles(food("pasta", name="Chicken Pasta", category="grain"))


def test_entree_and_another_main_are_not_combined():
    foods = [food("pizza", name="Pizza", category="grain"), food("chicken"), food("veg", calories=80, category="vegetable")]
    result = optimize(foods, target())
    assert not {"pizza", "chicken"} <= {f.id for f, _ in result.items}


def test_menu_order_does_not_change_result_and_duplicates_are_removed():
    foods = _demo_items()
    a = optimize(foods, target())
    b = optimize(list(reversed(foods)) + [foods[0]], target())
    assert [(f.id, size) for f, size in a.items] == [(f.id, size) for f, size in b.items]
    assert a.nutrition == total_for(a.items)
    assert len({f.id for f, _ in a.items}) == len(a.items) <= 4


def test_carbohydrate_goal_changes_selection():
    low = food("low", calories=200, protein=15, carbs=5, category="grain", portion_options=[1])
    high = food("high", calories=200, protein=15, carbs=45, category="grain", portion_options=[1])
    for desired, expected in [(5, "low"), (45, "high")]:
        result = optimize([low, high], target(200, carbs=desired, protein=15))
        assert [f.id for f, _ in result.items] == [expected]


def test_preferences_and_temporary_exclusions_are_separate():
    foods = [food("a", category="grain", portion_options=[1]), food("b", category="grain", portion_options=[1])]
    assert optimize(foods, target(200), ratings={"b": 1}).items[0][0].id == "b"
    assert optimize(foods, target(200), ratings={"b": -1}).items[0][0].id == "a"
    assert optimize(foods, target(200), options=PlannerOptions(avoided_terms=["b"])).items[0][0].id == "a"
    assert optimize(foods, target(200), recent={"a": 3}).items[0][0].id == "b"


def test_convenience_mode_prefers_one_station():
    foods = [food("main", calories=250, portion_options=[1], station="A"),
             food("sideA", calories=150, category="grain", portion_options=[1], station="A"),
             food("sideB", calories=150, category="grain", portion_options=[1], station="B")]
    result = optimize(foods, target(400), options=PlannerOptions(mode="convenient"))
    assert {f.station for f, _ in result.items} == {"A"}


def test_large_menu_keeps_a_vegetable_and_does_not_truncate_to_18():
    foods = [food(f"protein-{n}", calories=200, protein=40, carbs=0, category="protein") for n in range(25)]
    foods += [food("rice", calories=200, protein=4, category="grain"), food("veg", calories=60, protein=4, category="vegetable")]
    result = optimize(foods, target())
    assert "veg" in {f.id for f, _ in result.items}


def test_locks_preserve_exact_portions_and_alternatives_change_foods():
    foods = _demo_items()
    first = optimize(foods, target())
    kept, size = first.items[0]
    second = optimize(foods, target(), locked_items={kept.id: size}, previous=[f.id for f, _ in first.items])
    assert (kept, size) in second.items
    assert {f.id for f, _ in second.items} - {f.id for f, _ in first.items}
    assert optimize(foods, target(), locked_items={"missing": 1}).status == "invalid_lock"
    assert optimize(foods, target(), locked_items={kept.id: 0.33}).status == "invalid_lock"


def test_infeasible_and_zero_targets_do_not_relax_requirements():
    only = food("only", portion_options=[1])
    assert optimize([only], target(200), previous=["only"]).status == "infeasible"
    assert not optimize([only], target(0)).items
    assert not optimize([only], target(), ratings={"only": -1}).items


def test_timeout_fallback_keeps_locks_and_unique_foods(monkeypatch):
    monkeypatch.setattr(optimizer, "_solve", lambda *args: (None, "unknown"))
    result = optimize(_demo_items(), target(), locked_items={"demo-rice": 1})
    assert result.optimizer == "beam-fallback"
    assert (next(f for f in _demo_items() if f.id == "demo-rice"), 1) in result.items
    assert len({f.id for f, _ in result.items}) == len(result.items)
    assert result.nutrition.calories <= 650 * 1.28


def raw_nutrition(**changes):
    return {"food": {"id": "test", "name": "Test", "rounded_nutrition_info": {"calories": 100, "g_protein": 5, "g_carbs": 10, "g_fat": 4, **changes}}}


def test_missing_values_are_distinguished_from_zero():
    missing = _parse_food(raw_nutrition(), "Station")
    assert missing.nutrition_complete
    assert set(missing.missing_nutrients) == {"fiber_g", "sodium_mg"}
    zero = _parse_food(raw_nutrition(g_fiber=0, mg_sodium=0), "Station")
    assert zero.missing_nutrients == []
    for value in [None, "", "unknown", float("nan"), -1]:
        broken = _parse_food(raw_nutrition(g_protein=value), "Station")
        assert not broken.nutrition_complete
        assert "protein_g" in broken.missing_nutrients


def test_exact_calorie_solution_matches_small_exhaustive_search():
    foods = [food("a", 170, category="grain"), food("b", 130, category="vegetable"), food("c", 230)]
    possible = [sum(f.nutrition.calories * s for f, s in zip(foods, sizes)) for sizes in product([0, .5, 1, 1.5, 2], repeat=3)]
    desired = 615
    assert desired in possible
    result = optimize(foods, target(desired))
    assert abs(result.nutrition.calories - desired) <= 30
    assert result.status in {"optimal", "feasible"}


def test_garnishes_are_not_vegetable_sides_and_pound_units_are_bounded():
    topping = food('onions', calories=154, protein=4, category='vegetable', name='Julienne Red Onions', serving_unit='lbs')
    assert 'vegetable' not in roles(topping)
    assert 'garnish' in roles(topping)
    assert all(size * 16 <= 2.01 for size in portion_options(topping))


def test_station_name_does_not_override_food_classification():
    from app.nutrislice import classify_food
    assert classify_food('Broccoli and Roasted Peppers', 'Pasta') == 'vegetable'
    assert classify_food('Grated Parmesan Cheese', 'Pasta') == 'condiment'
    assert classify_food('Collard Greens', 'Comfort Station') == 'vegetable'
    assert classify_food('Pepper Jack Cheese', 'Deli Bar') == 'other'


def test_fallback_never_returns_conflicting_kept_mains(monkeypatch):
    monkeypatch.setattr(optimizer, '_solve', lambda *args: (None, 'unknown'))
    foods = [food('chicken'), food('tofu')]
    assert not optimize(foods, target(), locked_items={'chicken': 1, 'tofu': 1}).items


@pytest.mark.parametrize('index', [0, 1, 2])
def test_published_menus_produce_usable_discrete_plates(index):
    import json
    from pathlib import Path
    from app.optimizer import valid_selection
    snapshot = json.loads((Path(__file__).parent / 'fixtures/published_menus.json').read_text())
    foods = [MenuFood.model_validate(f) for f in snapshot['menus'][index]['foods']]
    result = optimize(foods, target(), seconds=.5)
    assert result.items
    assert valid_selection(result.items, target(), 'lunch')
    assert abs(result.nutrition.calories - 650) <= 65
    assert all(any(abs(size-value) < .00001 for value in portion_options(f)) for f,size in result.items)


def test_content_preferences_generalize_without_excluding_similar_foods():
    from app.preferences import predict_affinities
    foods = [food('new-chicken', name='Herb Grilled Chicken'), food('new-tofu', name='Roasted Tofu')]
    affinities = predict_affinities(foods, [('BBQ Chicken', 1), ('Sweet Tofu', -1)])
    assert affinities['new-chicken'] > 0
    assert affinities['new-tofu'] < 0
    assert optimize(foods, target(200), affinities=affinities).items[0][0].id == 'new-chicken'
    # Learned dislikes only lower a score; exact explicit dislikes exclude IDs.
    assert optimize([foods[1]], target(200), affinities=affinities).items
