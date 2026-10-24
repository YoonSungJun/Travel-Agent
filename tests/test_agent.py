import json

import httpx2
import pytest
from openai import OpenAI

from travel_agent.agent import AgentRequest, advise


def test_restaurant_search_uses_current_schedule_and_sources(trip):
    def respond(request):
        data = json.loads(request.content)
        assert data["tools"] == [{"type": "web_search"}]
        assert data["store"] is False
        context = json.loads(data["input"])
        assert context["selected_activity"]["area"] == "Asakusa"
        assert context["trip"]["hotel"]["area"] == "Ueno"
        return httpx2.Response(200, json={
            "id": "resp_offline", "object": "response", "created_at": 0,
            "status": "completed", "model": data["model"], "output": [{
                "id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "Asakusa restaurant candidate",
                             "annotations": [{"type": "url_citation", "url": "https://example.com",
                                              "title": "Source", "start_index": 0, "end_index": 7}]}]
            }]
        })

    trip.activities[0].area = "Asakusa"
    req = AgentRequest(stage="restaurants", message="Lunch nearby", activity_id="lunch", version=0)
    with OpenAI(api_key="offline-test-only", http_client=httpx2.Client(
        transport=httpx2.MockTransport(respond)
    )) as client:
        result = advise(trip, req, client=client)
    assert result["text"] == "Asakusa restaurant candidate"
    assert result["sources"] == [{"url": "https://example.com", "title": "Source"}]
    assert trip.activities[0].area == "Asakusa"


def test_deleted_activity_cannot_drive_restaurant_search(trip):
    req = AgentRequest(stage="restaurants", message="Lunch", activity_id="deleted", version=0)
    with pytest.raises(ValueError, match="선택"):
        advise(trip, req)


def test_missing_key_does_not_generate_fake_recommendations(trip, monkeypatch):
    monkeypatch.delenv("TRAVEL_AGENT_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TRAVEL_AGENT_API_KEY"):
        advise(trip, AgentRequest(stage="itinerary", message="Plan", version=0))
