from uuid import uuid4

import pytest

from test_auth import setup, register, bearer


def meal(at="2026-09-14T16:00:00Z", calories=650):
    return dict(id=str(uuid4()), consumed_at=at, hall_slug="north-ave-dining-hall", meal="lunch",
                items=[dict(id="food", name="Test plate", portion_label="1 serving", calories=calories)])


@pytest.mark.asyncio
async def test_history_is_owned_persistent_and_idempotent(setup):
    client, _ = setup
    one, two = await register(client), await register(client, "two@example.com")
    payload = meal()
    assert (await client.post("/api/meals", json=payload)).status_code == 401
    assert (await client.get("/api/meals?start=2026-09-14")).status_code == 401
    for _ in range(2):
        saved = await client.post("/api/meals", json=payload, headers=bearer(one))
        assert saved.status_code == 200, saved.text
        assert saved.json()["calories"] == 650
    history = await client.get("/api/meals?start=2026-09-14", headers=bearer(one))
    assert history.headers["cache-control"] == "no-store"
    assert history.json()["total_calories"] == 650
    assert len(history.json()["meals"]) == 1
    assert len(history.json()["days"]) == 7
    assert history.json()["days"][1]["calories"] == 0
    assert (await client.get("/api/meals?start=2026-09-14", headers=bearer(two))).json()["meals"] == []
    assert (await client.delete("/api/meals/" + payload["id"], headers=bearer(two))).status_code == 404
    assert (await client.delete("/api/meals/" + payload["id"], headers=bearer(one))).status_code == 204
    # Retrying an old POST after removal does not resurrect the meal.
    assert (await client.post("/api/meals", json=payload, headers=bearer(one))).json()["voided"] is True
    assert (await client.get("/api/meals?start=2026-09-14", headers=bearer(one))).json()["total_calories"] == 0


@pytest.mark.asyncio
async def test_eastern_boundaries_and_week_totals(setup):
    client, _ = setup
    headers = bearer(await register(client))
    for stamp, calories in [("2026-09-14T03:59:00Z", 100), ("2026-09-14T04:00:00Z", 200),
                            ("2026-09-14T23:30:00-04:00", 300), ("2026-09-15T04:00:00Z", 400)]:
        assert (await client.post("/api/meals", json=meal(stamp, calories), headers=headers)).status_code == 200
    result = (await client.get("/api/meals?start=2026-09-14", headers=headers)).json()
    assert result["days"][0]["calories"] == 500
    assert result["days"][1]["calories"] == 400
    assert result["total_calories"] == 900
    assert all(row["consumed_at"].endswith("Z") for row in result["meals"])


@pytest.mark.asyncio
async def test_dst_week_boundaries(setup):
    client, _ = setup
    headers = bearer(await register(client))
    # Spring-forward Sunday is 23 hours: next Monday starts at 04:00 UTC.
    for stamp in ["2026-03-02T04:59:00Z", "2026-03-02T05:00:00Z", "2026-03-09T03:59:00Z", "2026-03-09T04:00:00Z"]:
        assert (await client.post("/api/meals", json=meal(stamp, 100), headers=headers)).status_code == 200
    result = (await client.get("/api/meals?start=2026-03-02", headers=headers)).json()
    assert result["total_calories"] == 200
    assert result["days"][0]["calories"] == result["days"][6]["calories"] == 100


@pytest.mark.asyncio
async def test_meal_validation(setup):
    client, _ = setup
    headers = bearer(await register(client))
    for stamp in ["2026-09-14T12:00:00", "2099-01-01T12:00:00Z"]:
        assert (await client.post("/api/meals", json=meal(stamp), headers=headers)).status_code == 422
    for value in [-10, "NaN", 10001]:
        assert (await client.post("/api/meals", json=meal(calories=value), headers=headers)).status_code == 422
    payload = meal()
    payload["items"] = []
    assert (await client.post("/api/meals", json=payload, headers=headers)).status_code == 422
    payload = meal()
    payload["hall_slug"] = "invented-hall"
    assert (await client.post("/api/meals", json=payload, headers=headers)).status_code == 400
