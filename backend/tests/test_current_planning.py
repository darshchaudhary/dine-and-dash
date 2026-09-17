from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app import planning
from app.nutrislice import _demo_items, hall_details, meal_for_time
from app.schemas import MenuResponse
from test_auth import setup, register, bearer, PROFILE
from test_meals import meal

EASTERN = ZoneInfo("America/New_York")


@pytest.fixture
def menu_clock(monkeypatch):
    clock = [datetime(2026, 9, 14, 12, tzinfo=EASTERN)]
    monkeypatch.setattr(planning, "now", lambda: clock[0])
    async def menu(slug, at=None, meal=None):
        at = at or clock[0]
        foods = _demo_items()
        if slug == "brittain":
            foods = [food for food in foods if food.id == "demo-rice"]
        return MenuResponse(hall=hall_details(slug, at), date=at.date(), meal=meal or meal_for_time(at, slug),
                            items=foods, source="nutrislice", fetched_at=at)
    monkeypatch.setattr("app.meals.get_menu", menu)
    monkeypatch.setattr("app.recommendations.get_menu", menu)
    return clock


def test_closing_hours_boundaries():
    for at in [datetime(2026, 9, 14, 10, 59, tzinfo=EASTERN), datetime(2026, 9, 14, 22, tzinfo=EASTERN), datetime(2026, 9, 19, 12, tzinfo=EASTERN)]:
        with pytest.raises(HTTPException) as exc:
            planning.open_hall("brittain", at)
        assert exc.value.status_code == 409
    assert planning.open_hall("brittain", datetime(2026, 9, 14, 11, tzinfo=EASTERN)).open_now


@pytest.mark.asyncio
async def test_closed_hall_cannot_be_bypassed_with_old_timestamp(setup, menu_clock):
    client, _ = setup
    user = await register(client)
    headers = bearer(user)
    await client.put('/api/profiles/'+user['user']['id'], json=PROFILE, headers=headers)
    menu_clock[0] = datetime(2026, 9, 14, 22, tzinfo=EASTERN)
    response = await client.post('/api/recommendations', headers=headers, json={"user_id": user['user']['id'], "hall_slug": "north-ave-dining-hall", "at": "2026-09-14T12:00:00-04:00"})
    assert response.status_code == 409
    assert (await client.get('/api/meals/menu?hall_slug=north-ave-dining-hall', headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_current_menu_filter_hall_and_auth(setup, menu_clock):
    client, _ = setup
    assert (await client.get('/api/meals/menu?hall_slug=brittain')).status_code == 401
    headers = bearer(await register(client))
    result = await client.get('/api/meals/menu?hall_slug=north-ave-dining-hall&q=CHICKEN%20mindful', headers=headers)
    assert result.status_code == 200
    assert [item['id'] for item in result.json()['items']] == ['demo-chicken']
    assert result.json()['date'] == '2026-09-14' and result.json()['meal'] == 'lunch'
    assert (await client.get('/api/meals/menu?hall_slug=brittain&q=chicken', headers=headers)).json()['items'] == []
    assert (await client.get('/api/meals/menu?hall_slug=unknown', headers=headers)).status_code == 400


@pytest.mark.asyncio
async def test_extra_food_changes_target_and_counts_once(setup, menu_clock):
    client, _ = setup
    user = await register(client)
    headers = bearer(user)
    await client.put('/api/profiles/'+user['user']['id'], json=PROFILE, headers=headers)
    request = {"user_id": user['user']['id'], "hall_slug": "north-ave-dining-hall", "meal_calorie_target": 2500}
    before = (await client.post('/api/recommendations', json=request, headers=headers)).json()
    extra = dict(id=str(uuid4()), hall_slug='north-ave-dining-hall', menu_date='2026-09-14', meal='lunch', items=[dict(food_id='demo-chicken', servings=1.5, calories=1)])
    for _ in range(2):
        result = await client.post('/api/meals/from-menu', json=extra, headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()['calories'] == 345  # Calculated from menu, not client calories.
    after = (await client.post('/api/recommendations', json=request, headers=headers)).json()
    assert after['consumed_today_calories'] == 345
    assert after['remaining_today_calories'] == 1855
    assert after['target_calories'] == planning.remaining_target(2200, 345, 'lunch') < before['target_calories']
    history = (await client.get('/api/meals?start=2026-09-14', headers=headers)).json()
    assert len(history['meals']) == 1 and history['total_calories'] == 345
    await client.delete('/api/meals/'+extra['id'], headers=headers)
    assert (await client.post('/api/recommendations', json=request, headers=headers)).json()['target_calories'] == before['target_calories']


@pytest.mark.asyncio
async def test_stale_and_invalid_menu_selections_rejected(setup, menu_clock):
    client, _ = setup
    headers = bearer(await register(client))
    extra = dict(id=str(uuid4()), hall_slug='north-ave-dining-hall', menu_date='2026-09-14', meal='breakfast', items=[dict(food_id='demo-chicken', servings=1)])
    assert (await client.post('/api/meals/from-menu', json=extra, headers=headers)).status_code == 409
    extra['meal'] = 'lunch'
    extra['items'][0]['food_id'] = 'unknown'
    assert (await client.post('/api/meals/from-menu', json=extra, headers=headers)).status_code == 409
    extra['items'][0] = dict(food_id='demo-chicken', servings=-1)
    assert (await client.post('/api/meals/from-menu', json=extra, headers=headers)).status_code == 422
    extra['items'] = [dict(food_id='demo-chicken', servings=1)] * 2
    assert (await client.post('/api/meals/from-menu', json=extra, headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_goal_reached_and_account_day_isolation(setup, menu_clock):
    client, _ = setup
    first, other = await register(client), await register(client, 'other@example.com')
    headers = bearer(first)
    await client.put('/api/profiles/'+first['user']['id'], json=PROFILE, headers=headers)
    await client.post('/api/meals', json=meal('2026-09-13T16:00:00Z', 1500), headers=headers)
    await client.post('/api/meals', json=meal('2026-09-14T16:00:00Z', 1500), headers=bearer(other))
    request = {"user_id": first['user']['id'], "hall_slug": "north-ave-dining-hall"}
    assert (await client.post('/api/recommendations', json=request, headers=headers)).json()['consumed_today_calories'] == 0
    await client.post('/api/meals', json=meal('2026-09-14T16:00:00Z', 2300), headers=headers)
    result = (await client.post('/api/recommendations', json=request, headers=headers)).json()
    assert result['target_calories'] == result['remaining_today_calories'] == 0
    assert result['plate'] == []


@pytest.mark.asyncio
async def test_no_demo_fallback_in_search_or_recommendations(setup, menu_clock, monkeypatch):
    client, _ = setup
    async def unavailable(slug, *args):
        return MenuResponse(hall=hall_details(slug, menu_clock[0]), date='2026-09-14', meal='lunch', items=_demo_items(), source='demo', fetched_at=menu_clock[0])
    monkeypatch.setattr('app.meals.get_menu', unavailable)
    monkeypatch.setattr('app.recommendations.get_menu', unavailable)
    user = await register(client)
    headers = bearer(user)
    await client.put('/api/profiles/'+user['user']['id'], json=PROFILE, headers=headers)
    assert (await client.get('/api/meals/menu?hall_slug=brittain', headers=headers)).status_code == 503
    assert (await client.post('/api/recommendations', json={"user_id": user['user']['id'], "hall_slug": "brittain"}, headers=headers)).status_code == 503
