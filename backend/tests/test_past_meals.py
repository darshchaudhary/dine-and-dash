from datetime import datetime
from uuid import uuid4

import pytest

from app.nutrislice import _demo_items, hall_details
from app.schemas import MenuResponse
from test_auth import setup, register, bearer, PROFILE
from test_current_planning import menu_clock, EASTERN


def past(**changes):
    return dict(id=str(uuid4()), hall_slug="north-ave-dining-hall", local_time="2026-09-13T09:30:00",
                meal="breakfast", items=[dict(food_id="demo-chicken", servings=1.5)], **changes)


@pytest.mark.asyncio
async def test_past_search_uses_exact_date_hall_service(setup, menu_clock, monkeypatch):
    client, _ = setup
    headers = bearer(await register(client))
    seen = []
    async def menus(slug, at, meal):
        seen.append((slug, at.isoformat(), meal))
        foods = [food for food in _demo_items() if food.id == ("demo-rice" if meal == "breakfast" else "demo-chicken")]
        return MenuResponse(hall=hall_details(slug, at), date=at.date(), meal=meal, items=foods, source="nutrislice", fetched_at=at)
    monkeypatch.setattr("app.meals.get_menu", menus)
    query = dict(hall_slug="west-village", local_time="2026-09-13T09:30:00", meal="breakfast", q="BROWN global")
    assert (await client.get("/api/meals/past-menu", params=query)).status_code == 401
    response = await client.get("/api/meals/past-menu", params=query, headers=headers)
    assert response.status_code == 200, response.text
    assert [food["id"] for food in response.json()["items"]] == ["demo-rice"]
    assert seen == [("west-village", "2026-09-13T09:30:00-04:00", "breakfast")]
    query.update(local_time="2026-09-13T12:30:00", meal="lunch")
    assert (await client.get("/api/meals/past-menu", params=query, headers=headers)).json()["items"] == []


@pytest.mark.asyncio
async def test_backdated_calories_history_idempotency_and_today_budget(setup, menu_clock):
    client, _ = setup
    user = await register(client)
    headers = bearer(user)
    await client.put('/api/profiles/'+user['user']['id'], json=PROFILE, headers=headers)
    payload = past()
    for _ in range(2):
        response = await client.post("/api/meals/from-past-menu", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["calories"] == 345
    history = (await client.get("/api/meals", params={"start": "2026-09-07"}, headers=headers)).json()
    assert history["total_calories"] == 345 and len(history["meals"]) == 1
    assert history["days"][-1] == {"date": "2026-09-13", "calories": 345}
    stamp = datetime.fromisoformat(history["meals"][0]["consumed_at"].replace("Z", "+00:00"))
    assert stamp.astimezone(EASTERN).hour == 9
    request = {"user_id": user["user"]["id"], "hall_slug": payload["hall_slug"]}
    before = (await client.post("/api/recommendations", json=request, headers=headers)).json()
    assert before["consumed_today_calories"] == 0
    payload.update(id=str(uuid4()), local_time="2026-09-14T09:30:00")
    assert (await client.post("/api/meals/from-past-menu", json=payload, headers=headers)).status_code == 200
    after = (await client.post("/api/recommendations", json=request, headers=headers)).json()
    assert after["consumed_today_calories"] == 345 and after["target_calories"] < before["target_calories"]
    other = bearer(await register(client, "other-past@example.com"))
    assert (await client.get("/api/meals", params={"start": "2026-09-07"}, headers=other)).json()["total_calories"] == 0
    await client.delete('/api/meals/'+payload['id'], headers=headers)
    assert (await client.post("/api/recommendations", json=request, headers=headers)).json()["consumed_today_calories"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change,status", [
    ({"local_time": "2026-09-15T09:30:00"}, 422),
    ({"local_time": "2026-09-13T09:30:00Z"}, 422),
    ({"local_time": "1900-09-13T09:30:00"}, 422),
    ({"local_time": "2026-03-08T02:30:00"}, 422),
    ({"local_time": "2026-09-13T23:30:00", "meal": "dinner"}, 409),
    ({"meal": "lunch"}, 409),
    ({"meal": "snack"}, 422),
    ({"hall_slug": "unknown"}, 400),
    ({"hall_slug": "brittain"}, 409),
])
async def test_invalid_historical_context_rejected_for_search_and_save(setup, menu_clock, change, status):
    client, _ = setup
    headers = bearer(await register(client))
    payload = {**past(), **change}
    response = await client.post("/api/meals/from-past-menu", json=payload, headers=headers)
    assert response.status_code == status, response.text
    params = {key: payload[key] for key in ["hall_slug", "local_time", "meal"]}
    response = await client.get("/api/meals/past-menu", params=params, headers=headers)
    assert response.status_code == status, response.text


@pytest.mark.asyncio
async def test_closed_now_still_allows_past_meal_and_rejects_bad_foods(setup, menu_clock):
    client, _ = setup
    headers = bearer(await register(client))
    menu_clock[0] = datetime(2026, 9, 14, 23, tzinfo=EASTERN)
    payload = past()
    assert (await client.post("/api/meals/from-past-menu", json=payload, headers=headers)).status_code == 200
    for items, status in [([dict(food_id="not-in-menu", servings=1)], 409), ([dict(food_id="demo-rice", servings=-1)], 422), ([dict(food_id="demo-rice", servings=1)] * 2, 422)]:
        payload.update(id=str(uuid4()), items=items)
        assert (await client.post("/api/meals/from-past-menu", json=payload, headers=headers)).status_code == status


@pytest.mark.asyncio
async def test_historical_menu_failure_never_logs_demo(setup, menu_clock, monkeypatch):
    client, _ = setup
    headers = bearer(await register(client))
    async def missing(slug, at, meal):
        return MenuResponse(hall=hall_details(slug, at), date=at.date(), meal=meal, items=_demo_items(), source="demo", fetched_at=at)
    monkeypatch.setattr("app.meals.get_menu", missing)
    assert (await client.post("/api/meals/from-past-menu", json=past(), headers=headers)).status_code == 503
    assert (await client.get("/api/meals", params={"start": "2026-09-07"}, headers=headers)).json()["total_calories"] == 0
