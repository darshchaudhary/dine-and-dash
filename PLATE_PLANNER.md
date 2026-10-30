# Plate planner

The recommendation endpoint now runs a discrete OR-Tools CP-SAT optimizer, seeded by a bounded beam search. It chooses foods and portions together from the published hall/date/service menu. Synthetic demo food is never used in recommendations.

## How to use it

Open **Personalize my plate** on Today or My plate. Save planned meals, favorite or avoided foods, and a priority (balanced nutrition, favorites, or fewer station visits). The current service is always included; later selected services receive a share of the remaining calorie budget.

On My plate:

- **Keep on plate** preserves that food and its exact portion when rebuilding.
- **Like / Dislike** saves account-owned feedback. Dislikes exclude that exact food; likes increase its ranking. A small content-based learner also adjusts similar food names. Learned similarity never creates dietary labels or hard exclusions.
- **Find another plate** requires at least one different food. Previous foods receive an overlap penalty. If no alternative can preserve the kept foods and other requirements, the existing plate stays visible with an explanation.
- **Not available** temporarily excludes a food without changing taste preferences. Refresh clears these exclusions.
- Portion buttons follow the food's serving grid. Whole pieces and containers differ from scoopable foods. Kept portions cannot be edited until released.
- Saved likes and dislikes can be cleared in Personalize my plate, including foods no longer on today's menu.
- **Why this plate?** explains meal structure, calorie deviation, missing data, and an illustrative ±10% portion sensitivity scenario. The range is not a measured confidence interval.

## Optimization model

Each eligible food has Boolean variables for permitted portion choices; at most one portion can be selected per food. Plates have one to four distinct foods. Hard requirements include current-menu availability, explicit exclusions, verified dietary tags, permitted portions, and exact locks. Known allergens and ingredient aliases are filtered before solving; this is not a guarantee against missing labels or cross-contact.

Meal structure supports a composed entrée with sides or separate main/grain/produce components. Composed foods can cover multiple roles. A lunch/dinner plate has at most one main and one starch food; breakfast permits two. Soup, garnish, dessert, and condiment counts are bounded. Garnishes do not satisfy the produce role, and optional desserts have a 15% meal-calorie allowance. Structure deficits remain soft so a sparse menu can still produce a useful suggestion. The 300-kcal threshold relaxes role expectations for small meals.

The objective combines a strong penalty outside a ±10% calorie band, absolute calorie error, protein/fiber shortfalls, carbohydrate/fat deviations, sodium excess, missing-data penalties, station visits, preferences, recent repetition, and alternative overlap. Nutrient deviations are normalized with denominator floors, so units and zero remaining goals do not distort the score. Numeric targets are soft; infeasibility never relaxes dietary filters or food locks. Calories have an upper search bound of 128% of the meal target, consistent with the preceding planner's search policy.

Solver coefficients use tenths of nutrient units and integer objective weights. The solver uses one worker and a 300-ms search limit. An approximately 70-ms beam search supplies an initial feasible plate. Presolve is disabled because it consumed the interactive search budget on captured menus. Unknown/time-limited outcomes use the same-constraint fallback; proven infeasibility is kept separate. Work runs in a thread under a four-request semaphore, outside the API event loop. Menu data and role/portion features are cached; per-user responses are not shared or HTTP cached.

For very large menus, candidate pruning retains foods per category and preserves kept foods, rather than using the previous global top-18 cutoff. Canonical beam states remove duplicate food orderings and carry numeric totals to reduce overhead.

## Nutrition and data quality

Missing optional nutrients remain explicitly marked in `missing_nutrients`; numeric zeros are used only for serialization and known partial sums. Missing/invalid calories or primary macros prevent optimization. Nonfinite/negative nutrition and extreme batch records are rejected. Station names no longer override food names during classification. Pound-sized toppings receive ounce-sized portion options and are displayed in ounces.

Confirmed meal items now carry nutrient snapshots inside the existing meal-history JSON. Current-menu and past-menu logging calculate these snapshots from published nutrition. The user's adjusted plate records the displayed snapshot only after the user logs it. Old history rows remain readable. If a day's older records lack a nutrient, the app explains that the affected target uses saved daily proportions instead of claiming an accurate remaining nutrient budget. Voided meals and other accounts never contribute to consumption or repetition signals.

Explicit feedback uses a deterministic content-based learner with weighted food-name features. It works with sparse feedback and does not require invented training data. It is not a trained collaborative recommender or contextual bandit. Automated exploration and jointly optimizing all future service menus remain future extensions; the implemented planner uses explicit remaining-meal budgets and replans on each request.

## Storage, API, and deployment

Two additive tables (`planner_settings`, `food_preferences`) are created through the existing application startup. Existing profile and meal tables need no column migration. All preference routes authenticate the session and derive ownership from the authenticated account:

- `GET /api/planner`, `PUT /api/planner`
- `GET /api/planner/feedback`, `PUT /api/planner/feedback`
- `DELETE /api/planner/feedback/{food_id}`

Feedback writes verify the food against the current published menu. Clearing an existing preference does not require that food to be on today's menu. Recommendation requests additionally accept `locked_items` and `previous_item_ids`; the server still derives the current service, date, and calorie target itself.

Install the updated `backend/requirements.txt`, restart the API, and rebuild/redeploy the frontend. The hosted installation must deploy both sides before the new controls work. For isolated local development, override any saved hosted frontend URL:

```sh
# API: use your normal configured database, or an isolated SQLite preview database.
DATABASE_URL=sqlite+aiosqlite:////tmp/dinedash-preview.sqlite COOKIE_SECURE=false .venv/bin/uvicorn backend.app.main:app --port 8000

# Frontend, from frontend/
VITE_API_URL=http://localhost:8000 pnpm dev
```

The cookie override is only for the isolated HTTP localhost preview; production keeps its existing secure-cookie configuration.

## Verification and benchmark

Run backend tests from `backend/` with `../.venv/bin/python -m pytest -q`; build the frontend with `pnpm build` and run its existing checks with `pnpm test`.

`backend/tests/fixtures/published_menus.json` captures factual food/nutrient records from all three halls' published October 23, 2026 lunch menus. Ingredient prose is omitted. The fixture includes incomplete and anomalous records, so benchmark input reflects real adapter limitations.

Run `../.venv/bin/python scripts/benchmark_optimizer.py` from `backend/`. The report in `backend/optimizer-benchmark.json` compares the production optimizer and beam fallback using 450-, 650-, and 850-kcal goals, twice per hall. It records actual engine, solver status, food selections, nutrient score, calorie deviation, and wall time. Model construction is included; network and database latency are excluded. Runtime and solutions can vary with load and time limits. This small benchmark does not establish acceptance or nutritional outcomes; those require user feedback and broader menu coverage.
