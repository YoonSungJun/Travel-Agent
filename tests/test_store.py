import pytest

from travel_agent.store import ConflictError, Store


def test_survives_reopening_and_rejects_lost_update(tmp_path, flight):
    path = str(tmp_path / "trips.db")
    store = Store(path)
    trip = store.create()
    stale = store.get(trip.id)
    trip.set_flight(flight)
    store.save(trip, 0)
    assert Store(path).get(trip.id).flight == flight
    with pytest.raises(ConflictError):
        store.save(stale, 0)
    assert store.get(trip.id).flight == flight
