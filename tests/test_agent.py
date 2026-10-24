import json
import socket

import pytest

from travel_agent.agent import AgentRequest, build_prompt, preview_import


def test_prompt_uses_latest_restaurant_context_without_network(trip, monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("Network must not be used")
    monkeypatch.setattr(socket, "create_connection", forbid)
    monkeypatch.setenv("TRAVEL_AGENT_API_KEY", "unused-sentinel")
    trip.activities[0].area = "Asakusa"
    result = build_prompt(trip, AgentRequest(stage="restaurants", message="Lunch nearby",
                                            activity_id="lunch", version=0))
    assert '"area": "Asakusa"' in result["text"]
    assert '"area": "Ueno"' in result["text"]
    assert "unused-sentinel" not in result["text"]
    assert result["version"] == 0


def test_deleted_activity_rejected(trip):
    with pytest.raises(ValueError, match="선택"):
        build_prompt(trip, AgentRequest(stage="restaurants", message="Lunch",
                                       activity_id="deleted", version=0))


def test_itinerary_prompt_includes_import_contract(trip):
    result = build_prompt(trip, AgentRequest(stage="itinerary", message="Plan", version=0))
    assert '"activities"' in result["text"] and "JSON" in result["text"]


def test_import_preview_does_not_mutate_trip(trip, activity):
    before = trip.model_dump_json()
    item = activity.model_dump(mode="json", exclude={"id"})
    item["area"] = "Asakusa"
    text = '```json\n' + json.dumps({"activities": [item]}) + '\n```'
    result = preview_import(trip, text)
    assert result["activities"][0]["area"] == "Asakusa"
    assert result["activities"][0]["id"]
    assert trip.model_dump_json() == before


@pytest.mark.parametrize("text", ['not JSON', '{"activities": []}', '{"extra": []}',
                                 '```json\n{}\n```\n```json\n{}\n```'])
def test_bad_import_rejected(trip, text):
    with pytest.raises(ValueError):
        preview_import(trip, text)


def test_outside_trip_import_rejected(trip, activity):
    item = activity.model_dump(mode="json")
    item["day"] = "2026-11-01"
    with pytest.raises(ValueError, match="도착 시간"):
        preview_import(trip, json.dumps({"activities": [item]}))
