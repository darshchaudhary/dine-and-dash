"""Reproducible offline benchmark against a captured published-menu fixture.

Run from backend: ../.venv/bin/python scripts/benchmark_optimizer.py
The report compares the same filtered candidates and goals, including parsing,
model construction and total calculations; no API/network latency is included.
"""
import json
from pathlib import Path
from statistics import median
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.optimizer import beam_fallback, eligible, optimize, score
from app.schemas import MenuFood, MenuNutrition, PlannerOptions


def main():
    snapshot = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/published_menus.json").read_text())
    rows = []
    for menu in snapshot["menus"]:
        foods = [MenuFood.model_validate(food) for food in menu["foods"]]
        for calories in (450, 650, 850):
            target = MenuNutrition(calories=calories, protein_g=calories / 16, carbs_g=calories / 8, fat_g=calories / 30, fiber_g=calories / 80, sodium_mg=calories * 1.1)
            options = PlannerOptions()
            for method in ("cp-sat", "beam"):
                for repeat in range(2):
                    start = time.perf_counter()
                    if method == "cp-sat":
                        result = optimize(foods, target)
                    else:
                        candidates = eligible(foods, target, options, {}, {})
                        result = beam_fallback(candidates, target, options, {}, {}, {}, set(), "lunch")
                    elapsed = (time.perf_counter() - start) * 1000
                    rows.append(dict(hall=menu["hall"], calories=calories, method=method, engine=result.optimizer, ms=round(elapsed, 2), error=round(abs(result.nutrition.calories - calories), 2), score=round(score(result.items, target), 2), status=result.status, foods=len(result.items), plate=[dict(name=f.name, servings=s) for f, s in result.items]))
    summary = {}
    for method in ("cp-sat", "beam"):
        group = [row for row in rows if row["method"] == method]
        times = sorted(row["ms"] for row in group)
        summary[method] = dict(runs=len(group), median_ms=round(median(times), 2), p95_ms=times[min(len(times)-1, int(len(times)*.95))], median_calorie_error=median(row["error"] for row in group), mean_score=round(sum(row["score"] for row in group)/len(group), 2), empty_plates=sum(not row["foods"] for row in group), fallback_runs=sum(row["engine"] == "beam-fallback" for row in group))
    report = dict(source=snapshot["source"], menu_date=snapshot["menu_date"], summary=summary, runs=rows)
    output = Path(__file__).resolve().parents[1] / "optimizer-benchmark.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
