from datetime import datetime
from uuid import uuid4

import pytest

from app import planning
from app.models import FoodPreference
from app.nutrislice import _demo_items
from app.planner import context_for
from app.recommendations import _contains_allergen, _diet_allowed
from test_auth import setup, register, bearer, PROFILE
from test_current_planning import menu_clock, EASTERN


async def account(client, email="planner@example.com"):
    user = await register(client, email)
    headers = bearer(user)
    await client.put('/api/profiles/' + user['user']['id'], json=PROFILE, headers=headers)
    return user, headers


def test_remaining_meal_plan_allocates_actual_remaining_services():
    assert planning.remaining_target(2000, 500, "lunch", ["lunch", "dinner"]) == 700
    assert planning.remaining_target(2000, 500, "lunch", ["lunch"]) == 1500
    assert planning.remaining_target(2000, 500, "dinner", ["breakfast", "dinner"]) == 1500
    assert planning.remaining_target(2000, 2200, "dinner", ["dinner"]) == 0


@pytest.mark.asyncio
async def test_settings_and_feedback_are_persistent_private_and_reversible(setup, menu_clock, monkeypatch):
    client, maker = setup
    from app import planner
    from app.schemas import MenuResponse
    from app.nutrislice import hall_details
    async def menu(slug, at):
        return MenuResponse(hall=hall_details(slug, at), date=at.date(), meal="lunch", items=_demo_items(), source="nutrislice", fetched_at=at)
    monkeypatch.setattr(planner, "get_menu", menu)
    assert (await client.get('/api/planner')).status_code == 401
    user, headers = await account(client)
    _, other = await account(client, 'planner-other@example.com')
    options = dict(planned_meals=["lunch"], favorite_terms=[" Chicken ", "chicken"], avoided_terms=["tofu"], mode="favorites")
    response = await client.put('/api/planner', headers=headers, json=options)
    assert response.status_code == 200, response.text
    assert response.json()['favorite_terms'] == ['chicken']
    assert (await client.get('/api/planner', headers=headers)).json()['planned_meals'] == ['lunch']
    assert (await client.get('/api/planner', headers=other)).json()['planned_meals'] == ['breakfast', 'lunch', 'dinner']
    feedback = dict(hall_slug='north-ave-dining-hall', food_id='demo-chicken', rating=-1)
    assert (await client.put('/api/planner/feedback', headers=headers, json=feedback)).status_code == 200
    assert len((await client.get('/api/planner/feedback', headers=headers)).json()) == 1
    assert (await client.get('/api/planner/feedback', headers=other)).json() == []
    assert (await client.delete('/api/planner/feedback/demo-chicken', headers=other)).status_code == 200
    async with maker() as db:
        assert (await db.get(FoodPreference, (user['user']['id'], 'demo-chicken'))).rating == -1
    assert (await client.delete('/api/planner/feedback/demo-chicken', headers=headers)).status_code == 200
    assert (await client.get('/api/planner/feedback', headers=headers)).json() == []
    assert (await client.put('/api/planner/feedback', headers=headers, json={**feedback, 'food_id': 'not-on-menu'})).status_code == 409
    assert (await client.put('/api/planner', headers=headers, json={**options, 'planned_meals': []})).status_code == 422


@pytest.mark.asyncio
async def test_recommendations_use_saved_plan_ratings_and_portion_locks(setup, menu_clock):
    client, _ = setup
    user, headers = await account(client)
    await client.put('/api/planner', headers=headers, json=dict(planned_meals=['lunch'], avoided_terms=['tofu']))
    request = dict(user_id=user['user']['id'], hall_slug='north-ave-dining-hall')
    first = await client.post('/api/recommendations', headers=headers, json=request)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data['target_calories'] == 2200
    assert data['optimizer'] == 'cp-sat'
    assert data['plate']
    assert all(item['portion_options'] for item in data['plate'])
    assert all(item['id'] != 'demo-tofu' for item in data['plate'])
    item = data['plate'][0]
    alternate = await client.post('/api/recommendations', headers=headers, json={**request, 'previous_item_ids': [i['id'] for i in data['plate']], 'locked_items': [{'food_id': item['id'], 'servings': item['servings']}]})
    if alternate.status_code == 200:
        second = alternate.json()
        assert any(i['id'] == item['id'] and i['servings'] == item['servings'] for i in second['plate'])
        assert {i['id'] for i in second['plate']} - {i['id'] for i in data['plate']}
    else:
        assert alternate.status_code == 409
    bad = await client.post('/api/recommendations', headers=headers, json={**request, 'locked_items': [{'food_id': item['id'], 'servings': .33}]})
    assert bad.status_code == 409


@pytest.mark.asyncio
async def test_logged_nutrition_updates_remaining_targets_and_legacy_data_is_explicit(setup, menu_clock):
    client, maker = setup
    user, headers = await account(client)
    request = dict(user_id=user['user']['id'], hall_slug='north-ave-dining-hall')
    baseline = (await client.post('/api/recommendations', headers=headers, json=request)).json()
    food = dict(id='eaten', name='Breakfast', portion_label='1 serving', calories=500,
                nutrition=dict(calories=500, protein_g=60, carbs_g=30, fat_g=10, fiber_g=10, sodium_mg=500))
    body = dict(id=str(uuid4()), consumed_at='2026-09-14T12:00:00Z', hall_slug='north-ave-dining-hall', meal='breakfast', items=[food])
    assert (await client.post('/api/meals', headers=headers, json=body)).status_code == 200
    result = (await client.post('/api/recommendations', headers=headers, json=request)).json()
    assert result['consumed_today_calories'] == 500
    assert result['progress']['target']['protein_g'] < baseline['progress']['target']['protein_g']
    async with maker() as db:
        context = await context_for(db, user['user']['id'], menu_clock[0])
        assert context.consumed.protein_g == 60
        assert context.recent['eaten'] == 1
    del food['nutrition']
    body['id'] = str(uuid4())
    await client.post('/api/meals', headers=headers, json=body)
    result = (await client.post('/api/recommendations', headers=headers, json=request)).json()
    assert any('lack complete nutrient' in line for line in result['explanation'])


def test_diet_filters_match_words_and_require_halal_evidence():
    chicken = _demo_items()[0]
    assert not _diet_allowed(chicken, {'vegetarian'})
    assert not _diet_allowed(chicken, {'halal'})
    assert _diet_allowed(chicken.model_copy(update={'dietary_tags': ['halal']}), {'halal'})
    assert not _diet_allowed(chicken.model_copy(update={'name': 'Ham sandwich'}), {'vegetarian'})
    assert not _diet_allowed(chicken.model_copy(update={'name': 'Champignon mushrooms', 'ingredients': '', 'dietary_tags': []}), {'vegetarian'})
    assert _diet_allowed(chicken.model_copy(update={'name': 'Champignon mushrooms', 'ingredients': '', 'dietary_tags': ['halal']}), {'halal'})
    assert _contains_allergen(chicken.model_copy(update={'ingredients': 'soy sauce'}), {'soy'})
    assert _contains_allergen(chicken.model_copy(update={'ingredients': 'whey protein'}), {'milk'})


def test_partial_nutrient_snapshot_does_not_claim_missing_values_are_zero():
    from app.meals import EatenItem
    item = EatenItem(id='partial', name='Meal', portion_label='1 portion', calories=300, nutrition={'calories': 300, 'protein_g': 20})
    assert set(item.missing_nutrients) == {'carbs_g', 'fat_g', 'fiber_g', 'sodium_mg'}
