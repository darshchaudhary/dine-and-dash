"""Discrete, bounded plate planning. No network or database work runs here.

Nutrient goals are soft; availability, restrictions, portion grids and locks are
hard. The caller filters restrictions before invoking either solver or fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import math
import time

from ortools.sat.python import cp_model

from .schemas import MenuFood, MenuNutrition, PlannerOptions

NUTRIENTS = tuple(MenuNutrition.model_fields)
OBJECTIVE_SCALE = 1_000_000
NORMALIZATION = {"calories": 100, "protein_g": 10, "carbs_g": 20, "fat_g": 5, "fiber_g": 5, "sodium_mg": 300}
SCALE = 10  # Preserve tenths of a gram/mg/kcal in integer constraints.
SOLVE_SECONDS = 0.3


@dataclass
class CandidatePlate:
    items: list[tuple[MenuFood, float]] = field(default_factory=list)
    nutrition: MenuNutrition = field(default_factory=MenuNutrition)
    optimizer: str = "cp-sat"
    status: str = "not_run"
    solve_ms: float = 0
    template: str = "Flexible meal"


@lru_cache(maxsize=4096)
def _roles(name: str, category: str, protein: float) -> tuple[str, ...]:
    text = name.casefold()
    roles = {category}
    if category == "vegetable" and any(term in text for term in ("onion", "jalapeno", "banana pepper", "green pepper", "grape tomato", "diced tomato", "shredded carrot", "shredded red cabbage")) and not any(term in text for term in ("roast", "saute", "steam", "grill")):
        roles.discard("vegetable")
        roles.add("garnish")
    # Roles describe components; a composed entrée can cover multiple roles.
    composed = any(term in text for term in ("pizza", "lasagna", "sandwich", "burrito", "taco", "burger", "casserole", "stir fry", "stir-fry", "grain bowl", "rice bowl", "pasta"))
    if "soup" in text:
        roles.add("soup")
    if composed:
        roles.add("composed")
        if protein >= 10:
            roles.add("protein")
        if any(term in text for term in ("pizza", "lasagna", "sandwich", "burrito", "taco", "burger", "pasta", "rice", "grain")):
            roles.add("grain")
    if any(term in text for term in ("yogurt", "oatmeal", "pancake", "waffle", "omelet", "scrambled egg")):
        roles.add("breakfast")
    return tuple(sorted(roles))


def roles(food: MenuFood) -> set[str]:
    return set(food.roles or _roles(food.name, food.category, food.nutrition.protein_g))


@lru_cache(maxsize=4096)
def _portions(name: str, unit: str, amount: float) -> tuple[float, ...]:
    unit = unit.casefold().rstrip("s")
    if unit in {"ea", "each", "single patty", "strip", "round", "pizza"} or any(word in unit for word in ("container", "package", "bottle", "carton")):
        if unit in {"round", "pizza"} and amount < 1:
            return (1.0, 2.0)  # Fraction of a whole pizza already specified upstream.
        return (1.0, 2.0)
    if unit in {"lb", "pound"}:
        return tuple(round(ounces / (16 * amount), 6) for ounces in (1, 2, 3, 4))
    if unit in {"piece", "slice", "egg", "patty", "breast", "sandwich", "burger", "wrap", "muffin", "cookie", "banana", "apple"}:
        return tuple(round(n / amount, 6) for n in range(1, min(4, math.floor(amount * 2)) + 1)) or (1.0,)
    if unit in {"tbsp", "tsp", "tablespoon", "teaspoon"}:
        return (0.5, 1.0)
    return (0.5, 1.0, 1.5, 2.0)


def portion_options(food: MenuFood) -> list[float]:
    values = food.portion_options or _portions(food.name, food.serving_unit, max(food.serving_amount, 0.01))
    values = sorted({float(value) for value in values if 0 < value <= 3})
    if "garnish" in roles(food):
        unit = food.serving_unit.casefold().rstrip("s")
        ounces = food.serving_amount * (16 if unit in {"lb", "pound"} else 1)
        if unit in {"oz", "ounce", "lb", "pound"}:
            values = [v for v in values if v * ounces <= 2.01]
        else:
            values = [v for v in values if v <= 1]
    if food.category in {"condiment", "dessert"}:
        values = [v for v in values if v <= 1]
    return values


def total_for(items: list[tuple[MenuFood, float]]) -> MenuNutrition:
    return MenuNutrition(**{key: sum(getattr(food.nutrition, key) * servings for food, servings in items) for key in NUTRIENTS})


def template_for(items, meal):
    found = set().union(*(roles(food) for food, _ in items)) if items else set()
    if meal == "breakfast":
        return "Breakfast plate"
    if "composed" in found:
        return "Entrée with sides"
    if {"protein", "grain", "vegetable"} <= found:
        return "Main, grain and vegetables"
    if "protein" in found and "vegetable" in found:
        return "Main and vegetables"
    return "Flexible meal"


def category_limits(meal):
    return (("protein", 2), ("grain", 2 if meal == "breakfast" else 1), ("other", 1), ("dessert", 1), ("condiment", 1), ("composed", 1), ("garnish", 1), ("soup", 1))


def valid_selection(items, target, meal):
    if not items or len(items) > 4 or sum(f.nutrition.calories * size for f, size in items) > target.calories * 1.28 + 0.05:
        return False
    if sum("composed" in roles(f) or f.category == "protein" for f,_ in items) > (2 if meal == "breakfast" else 1):
        return False
    if sum(f.nutrition.calories * size for f,size in items if f.category == "dessert") > target.calories * .15 + .05:
        return False
    return all(sum(category in roles(f) if category in {"composed", "garnish", "soup"} else f.category == category for f,_ in items) <= limit for category,limit in category_limits(meal))


def preference_cost(food, options, ratings, recent, affinities=None):
    text = f"{food.name} {food.ingredients}".casefold()
    favorite = any(term in text for term in options.favorite_terms)
    rating = ratings.get(food.id, 0)
    weight = 9 if options.mode == "favorites" else 4
    return -weight * (int(favorite) + max(0, rating) + (affinities or {}).get(food.id, 0)) + 2 * min(3, recent.get(food.id, 0))


def eligible(items, target, options, ratings, locks, affinities=None):
    seen = set()
    result = []
    for food in sorted(items, key=lambda f: f.id):
        if food.id in seen:
            continue
        seen.add(food.id)
        text = f"{food.name} {food.ingredients}".casefold()
        if not food.nutrition_complete or ratings.get(food.id) == -1 or any(term in text for term in options.avoided_terms):
            continue
        if food.nutrition.calories <= 0 or not all(math.isfinite(getattr(food.nutrition, key)) and getattr(food.nutrition, key) >= 0 for key in NUTRIENTS):
            continue
        # Check each actual portion, not the unscaled nutrition record.
        if any(food.nutrition.calories * size <= target.calories * 1.28 for size in portion_options(food)):
            result.append(food)
    # Retain role diversity on unusually large menus. Locks survive pruning.
    if len(result) > 120:
        groups = {}
        for food in result:
            groups.setdefault(food.category, []).append(food)
        result = [food for group in groups.values() for food in sorted(group, key=lambda f: (f.id not in locks, preference_cost(f, options, ratings, {}, affinities), -(f.nutrition.protein_g + f.nutrition.fiber_g) / max(f.nutrition.calories, 1), f.id))[:24]]
    return result


def score(items, target, options=None, ratings=None, recent=None, meal="lunch", affinities=None):
    options, ratings, recent = options or PlannerOptions(), ratings or {}, recent or {}
    total = total_for(items)
    calorie_error = abs(total.calories - target.calories)
    value = 100 * calorie_error / max(target.calories, 1) + 1000 * max(0, calorie_error - target.calories * 0.1) / max(target.calories, 1)
    weights = {"protein_g": 35, "carbs_g": 15, "fat_g": 8, "fiber_g": 10, "sodium_mg": 28}
    for key, weight in weights.items():
        actual, goal = getattr(total, key), getattr(target, key)
        error = max(0, actual - goal) if key == "sodium_mg" else max(0, goal - actual) if key in {"protein_g", "fiber_g"} else abs(actual - goal)
        value += weight * error / max(goal, NORMALIZATION[key])
    found = set().union(*(roles(food) for food, _ in items)) if items else set()
    if target.calories >= 300:
        value += 22 * ("protein" not in found) + (8 if meal == "breakfast" else 16) * (not ({"fruit", "vegetable"} & found))
        value += 6 * ("grain" not in found)
    value += (10 if options.mode == "convenient" else 2) * len({f.station for f, _ in items})
    value += sum(preference_cost(f, options, ratings, recent, affinities) + len(f.missing_nutrients) * 4 for f, _ in items)
    return value


def _solve(foods, target, options, ratings, recent, locks, previous, meal, seconds, hint=None, affinities=None):
    model = cp_model.CpModel()
    selections, chosen, portions = {}, {}, {}
    objective = []
    for food in foods:
        values = [v for v in portion_options(food) if food.nutrition.calories * v <= target.calories * 1.28]
        portions[food.id] = values
        variables = [model.new_bool_var(f"{food.id}:{v}") for v in values]
        selections[food.id] = variables
        chosen[food.id] = model.new_bool_var(f"use:{food.id}")
        model.add(sum(variables) == chosen[food.id])
        if food.id in locks:
            if not any(abs(v - locks[food.id]) < 1e-5 for v in values):
                return None, "invalid_lock"
            for v, variable in zip(values, variables):
                model.add(variable == int(abs(v - locks[food.id]) < 1e-5))
        cost = preference_cost(food, options, ratings, recent, affinities) + len(food.missing_nutrients) * 4
        if food.category in {"condiment", "dessert"}:
            cost += 4
        if food.id in previous and food.id not in locks:
            cost += 5
        objective.append(round(cost * OBJECTIVE_SCALE) * chosen[food.id])
    model.add(sum(chosen.values()) >= 1)
    model.add(sum(chosen.values()) <= 4)
    # Distinct alternative must contain a new food, not just new quantities.
    if previous:
        model.add(sum(chosen[f.id] for f in foods if f.id not in previous) >= 1)
    # A composed entrée already supplies the main. Avoid adding another main
    # simply to hit macros; breakfast may combine two smaller protein foods.
    model.add(sum(chosen[f.id] for f in foods if "composed" in roles(f) or f.category == "protein") <= (2 if meal == "breakfast" else 1))
    # Flexible templates: either a composed entrée + sides or separate components.
    for category, maximum in category_limits(meal):
        model.add(sum(chosen[f.id] for f in foods if (category in roles(f) if category in {"composed", "garnish", "soup"} else f.category == category)) <= maximum)
    # Toppings cannot stand in for a vegetable side. Desserts stay optional.
    model.add(sum(round(f.nutrition.calories * size * SCALE) * variable for f in foods if f.category == "dessert" for size, variable in zip(portions[f.id], selections[f.id])) <= round(target.calories * .15 * SCALE))
    for group, weight in (({"protein"}, 22), ({"fruit", "vegetable"}, 8 if meal == "breakfast" else 16), ({"grain"}, 6)):
        if target.calories >= 300:
            missing = model.new_bool_var(f"missing:{group}")
            model.add(sum(chosen[f.id] for f in foods if roles(f) & group) + missing >= 1)
            objective.append(weight * OBJECTIVE_SCALE * missing)
    for station in sorted({f.station for f in foods}):
        used = model.new_bool_var(f"station:{station}")
        station_items = [chosen[f.id] for f in foods if f.station == station]
        model.add_max_equality(used, station_items)
        objective.append((10 if options.mode == "convenient" else 2) * OBJECTIVE_SCALE * used)
    upper = max(1, round(target.calories * 1.28 * SCALE))
    weights = {"calories": 100, "protein_g": 35, "carbs_g": 15, "fat_g": 8, "fiber_g": 10, "sodium_mg": 28}
    for key, weight in weights.items():
        goal = round(getattr(target, key) * SCALE)
        expression = sum(round(getattr(food.nutrition, key) * size * SCALE) * variable for food in foods for size, variable in zip(portions[food.id], selections[food.id]))
        bound = max(upper, sum(sorted((max([round(getattr(food.nutrition, key) * v * SCALE) for v in portions[food.id]] or [0]) for food in foods), reverse=True)[:4]), goal)
        delta = model.new_int_var(0, bound, f"deviation:{key}")
        if key in {"protein_g", "fiber_g"}:
            model.add(delta >= goal - expression)
        elif key == "sodium_mg":
            model.add(delta >= expression - goal)
        else:
            model.add_abs_equality(delta, expression - goal)
        objective.append(max(1, round(weight * OBJECTIVE_SCALE / max(goal, NORMALIZATION[key] * SCALE))) * delta)
        if key == "calories":
            model.add(expression <= upper)
            outside = model.new_int_var(0, bound, "outside_calorie_band")
            model.add(outside >= delta - round(goal * 0.1))
            objective.append(max(1, round(1000 * OBJECTIVE_SCALE / max(goal, NORMALIZATION[key] * SCALE))) * outside)
    if hint and hint.items:
        wanted = {food.id: size for food, size in hint.items}
        for food in foods:
            for size, variable in zip(portions[food.id], selections[food.id]):
                model.add_hint(variable, int(food.id in wanted and abs(wanted[food.id] - size) < 1e-5))
    model.minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    # Presolve dominated the short interactive budget on published menus.
    solver.parameters.cp_model_presolve = False
    solver.parameters.max_presolve_iterations = 1
    solver.parameters.cp_model_probing_level = 0
    solver.parameters.symmetry_level = 0
    status = solver.solve(model)
    label = solver.status_name(status).lower()
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, label
    selected = [(food, size) for food in foods for size, variable in zip(portions[food.id], selections[food.id]) if solver.value(variable)]
    return CandidatePlate(items=selected, nutrition=total_for(selected), status=label, template=template_for(selected, meal)), label


def beam_fallback(foods, target, options, ratings, recent, locks, previous, meal, budget=0.12, affinities=None):
    """Canonical beam states carry numeric totals, avoiding repeated model parsing."""
    started = time.monotonic()
    by_id = {f.id: f for f in foods}
    food_roles = {f.id: roles(f) for f in foods}
    costs = {f.id: preference_cost(f, options, ratings, recent, affinities) + len(f.missing_nutrients) * 4 + (4 if f.category in {"condiment", "dessert"} else 0) + (5 if f.id in previous and f.id not in locks else 0) for f in foods}
    variants = [(f, size, tuple(getattr(f.nutrition, k) * size for k in NUTRIENTS)) for f in foods if f.id not in locks for size in portion_options(f)]
    goals = tuple(getattr(target, key) for key in NUTRIENTS)
    def evaluate(signature, totals):
        error = abs(totals[0] - goals[0])
        value = 100 * error / max(goals[0], 1) + 1000 * max(0, error - goals[0] * .1) / max(goals[0], 1)
        for index, weight in ((1, 35), (2, 15), (3, 8), (4, 10), (5, 28)):
            actual, goal = totals[index], goals[index]
            error = max(0, actual-goal) if index == 5 else max(0, goal-actual) if index in {1,4} else abs(actual-goal)
            value += weight * error / max(goal, NORMALIZATION[NUTRIENTS[index]])
        found = set().union(*(food_roles[key] for key, _ in signature))
        if target.calories >= 300:
            value += 22 * ("protein" not in found) + (8 if meal == "breakfast" else 16) * (not ({"fruit", "vegetable"} & found)) + 6 * ("grain" not in found)
        value += (10 if options.mode == "convenient" else 2) * len({by_id[key].station for key, _ in signature})
        return value + sum(costs[key] for key, _ in signature)
    seed = tuple(sorted(locks.items()))
    seed_totals = tuple(sum(getattr(by_id[key].nutrition, k) * size for key,size in seed) for k in NUTRIENTS)
    if seed and not valid_selection([(by_id[key], size) for key, size in seed], target, meal):
        return CandidatePlate(optimizer="beam-fallback", status="no_solution")
    beam = [(seed, seed_totals)]
    finished = []
    if seed and (not previous or any(key not in previous for key,_ in seed)):
        finished.append((evaluate(seed, seed_totals), seed))
    for depth in range(len(seed), 4):
        expanded = {}
        for signature, totals in beam:
            used = {key for key,_ in signature}
            existing = [by_id[key] for key,_ in signature]
            for f, size, vector in variants:
                if f.id in used:
                    continue
                combined = tuple(a+b for a,b in zip(totals, vector))
                if combined[0] > target.calories * 1.28:
                    continue
                selected = [*existing, f]
                if sum("composed" in food_roles[item.id] or item.category == "protein" for item in selected) > (2 if meal == "breakfast" else 1):
                    continue
                if any(sum(category in food_roles[item.id] if category in {"composed", "garnish", "soup"} else item.category == category for item in selected) > limit for category,limit in category_limits(meal)):
                    continue
                candidate = tuple(sorted((*signature, (f.id,size))))
                if sum(by_id[key].nutrition.calories * portion for key,portion in candidate if by_id[key].category == "dessert") > target.calories*.15:
                    continue
                if candidate not in expanded:
                    expanded[candidate] = (evaluate(candidate, combined), combined)
            if time.monotonic()-started > budget:
                break
        ranked = sorted(expanded, key=lambda signature: (expanded[signature][0], signature))
        if not ranked:
            break
        # Reserve slots for smaller partial meals that can accept another side.
        keep = list(dict.fromkeys(ranked[:36] + sorted(ranked,key=lambda c:expanded[c][1][0])[:12]))
        beam = [(c,expanded[c][1]) for c in keep]
        finished.extend((expanded[c][0],c) for c in ranked[:60] if not previous or any(key not in previous for key,_ in c))
        if time.monotonic()-started > budget:
            break
    signature = min(finished, default=(0,()))[1]
    items = [(by_id[key],size) for key,size in signature]
    return CandidatePlate(items=items, nutrition=total_for(items), optimizer="beam-fallback", status="feasible" if items else "no_solution", template=template_for(items,meal))


def optimize(items, target, *, options=None, ratings=None, recent=None, locked_items=None, previous=None, meal="lunch", seconds=SOLVE_SECONDS, affinities=None):
    started = time.monotonic()
    options, ratings, recent = options or PlannerOptions(), ratings or {}, recent or {}
    locks, previous = locked_items or {}, set(previous or [])
    if target.calories <= 0:
        return CandidatePlate(status="goal_reached")
    foods = eligible(items, target, options, ratings, locks, affinities)
    if set(locks) - {f.id for f in foods} or any(not any(abs(v - locks[f.id]) < 1e-5 for v in portion_options(f)) for f in foods if f.id in locks):
        return CandidatePlate(status="invalid_lock")
    if not foods:
        return CandidatePlate(status="no_candidates")
    hint = beam_fallback(foods, target, options, ratings, recent, locks, previous, meal, budget=0.07, affinities=affinities)
    result, status = _solve(foods, target, options, ratings, recent, locks, previous, meal, seconds, hint, affinities)
    if result is None:
        if status in {"unknown", "model_invalid"}:
            result = hint if hint.items else beam_fallback(foods, target, options, ratings, recent, locks, previous, meal, affinities=affinities)
        else:
            result = CandidatePlate(status=status)
    result.solve_ms = round((time.monotonic() - started) * 1000, 2)
    return result
