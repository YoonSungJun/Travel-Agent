import threading

import pytest

from travel_agent.domain import Activity, Flight, Hotel, Trip
from travel_agent.server import make_server


@pytest.fixture
def flight():
    return Flight(origin="ICN", destination="Tokyo", arrival_date="2026-11-10",
                  arrival_time="10:00", departure_date="2026-11-13", departure_time="18:00")


@pytest.fixture
def hotel():
    return Hotel(name="Tokyo Hotel", area="Ueno", check_in="2026-11-10", check_out="2026-11-13")


@pytest.fixture
def activity():
    return Activity(id="lunch", day="2026-11-11", start="12:00", end="13:00",
                    title="Lunch", area="Ueno", kind="meal")


@pytest.fixture
def trip(flight, hotel, activity):
    item = Trip(id="example")
    item.set_flight(flight)
    item.set_hotel(hotel)
    item.set_activities([activity])
    return item


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.delenv("TRAVEL_AGENT_API_KEY", raising=False)
    httpd = make_server(port=0, db_path=str(tmp_path / "trips.sqlite3"))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join(timeout=5)
    httpd.server_close()
