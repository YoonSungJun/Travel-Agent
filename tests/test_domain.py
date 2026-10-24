from datetime import time

import pytest
from pydantic import ValidationError

from travel_agent.domain import Activity, Flight, Hotel, Trip


def test_order_is_enforced(hotel, activity):
    trip = Trip(id="test")
    assert trip.stage == "flight"
    with pytest.raises(ValueError, match="항공권"):
        trip.set_hotel(hotel)
    with pytest.raises(ValueError, match="먼저"):
        trip.set_activities([activity])


def test_flight_update_invalidates_downstream(trip, flight):
    trip.set_flight(flight)
    assert trip.hotel and trip.activities
    changed = flight.model_copy(update={"destination": "Osaka"})
    trip.set_flight(changed)
    assert trip.hotel is None and trip.activities == [] and trip.stage == "hotel"


def test_hotel_update_invalidates_itinerary(trip, hotel):
    trip.set_hotel(hotel)
    assert trip.activities
    trip.set_hotel(hotel.model_copy(update={"area": "Shinjuku"}))
    assert not trip.activities and trip.flight and trip.stage == "itinerary"


def test_hotel_outside_flight_window(trip):
    hotel = Hotel(name="Wrong", area="Tokyo", check_in="2026-11-09", check_out="2026-11-13")
    with pytest.raises(ValueError, match="숙박 날짜"):
        trip.set_hotel(hotel)


@pytest.mark.parametrize("changes", [
    {"day": "2026-11-09"}, {"day": "2026-11-10", "start": "09:00", "end": "10:00"},
    {"day": "2026-11-13", "start": "18:00", "end": "19:00"},
])
def test_activity_must_fit_flight_window(trip, activity, changes):
    candidate = Activity.model_validate({**activity.model_dump(mode="json"), **changes})
    with pytest.raises(ValueError, match="도착 시간"):
        trip.set_activities([candidate])


def test_overlapping_or_duplicate_items_rejected(trip, activity):
    with pytest.raises(ValueError, match="중복"):
        trip.set_activities([activity, activity])
    other = activity.model_copy(update={"id": "other", "start": time(12, 30)})
    with pytest.raises(ValueError, match="겹칩니다"):
        trip.set_activities([activity, other])


def test_modify_and_remove_activity_keeps_bookings(trip, activity):
    updated = activity.model_copy(update={"area": "Asakusa"})
    trip.set_activities([updated])
    assert trip.activities[0].area == "Asakusa" and trip.stage == "restaurants"
    trip.set_activities([])
    assert trip.flight and trip.hotel and trip.stage == "itinerary"


def test_invalid_flight_dates(flight):
    with pytest.raises(ValidationError):
        Flight.model_validate({**flight.model_dump(mode="json"), "departure_date": "2026-11-09"})
