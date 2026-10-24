import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


def call(server, path, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    request = Request(server + path, data=body, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_complete_workflow_and_persistence(server, flight, hotel, activity):
    status, trip = call(server, "/api/trips", {})
    assert status == 201 and trip["stage"] == "flight"
    path = f"/api/trips/{trip['id']}"
    for action, model, stage in [("flight", flight, "hotel"), ("hotel", hotel, "itinerary")]:
        status, trip = call(server, f"{path}/{action}",
                            {"version": trip["version"], "data": model.model_dump(mode="json")})
        assert status == 200 and trip["stage"] == stage
    status, trip = call(server, f"{path}/activities", {"version": trip["version"],
                       "data": [activity.model_dump(mode="json")]})
    assert status == 200 and trip["stage"] == "restaurants"
    assert call(server, path)[1] == trip
    status, error = call(server, f"{path}/activities", {"version": 0, "data": []})
    assert status == 409 and "변경" in error["error"]
    assert call(server, path)[1]["activities"] == trip["activities"]


def test_early_hotel_is_rejected(server, hotel):
    _, trip = call(server, "/api/trips", {})
    status, result = call(server, f"/api/trips/{trip['id']}/hotel",
                          {"version": 0, "data": hotel.model_dump(mode="json")})
    assert status == 400 and "먼저" in result["error"]


def test_missing_key_is_actionable(server):
    _, trip = call(server, "/api/trips", {})
    status, result = call(server, f"/api/trips/{trip['id']}/advice",
                          {"version": 0, "stage": "flight", "message": "Find flights"})
    assert status == 503 and "TRAVEL_AGENT_API_KEY" in result["error"]


def test_cross_origin_mutation_rejected(server):
    status, _ = call(server, "/api/trips", {}, {"Origin": "https://example.org"})
    assert status == 403


@pytest.mark.parametrize("payload", [[], {"version": "wrong"}, {"version": 0, "data": {}}])
def test_bad_input_does_not_mutate(server, payload):
    _, trip = call(server, "/api/trips", {})
    status, _ = call(server, f"/api/trips/{trip['id']}/flight", payload)
    assert status == 400
    assert call(server, f"/api/trips/{trip['id']}")[1] == trip


def test_unknown_trip_and_health(server):
    assert call(server, "/api/trips/invalid")[0] == 404
    assert call(server, "/api/health")[1] == {"ok": True, "ai_configured": False}


def test_static_ui_is_served(server):
    with urlopen(server + "/", timeout=10) as response:
        assert response.status == 200
        assert "차곡여행" in response.read().decode()
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
