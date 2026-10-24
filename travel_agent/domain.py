from datetime import date, datetime, time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Flight(Model):
    origin: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    arrival_date: date
    arrival_time: time
    departure_date: date
    departure_time: time
    description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def valid_dates(self):
        if datetime.combine(self.arrival_date, self.arrival_time) >= datetime.combine(
            self.departure_date, self.departure_time
        ):
            raise ValueError("현지 도착 시간은 귀국편 현지 출발 시간보다 빨라야 합니다.")
        if self.arrival_time.tzinfo or self.departure_time.tzinfo:
            raise ValueError("항공 시간은 목적지 현지 시간으로 입력하세요.")
        return self


class Hotel(Model):
    name: str = Field(min_length=1, max_length=200)
    area: str = Field(min_length=1, max_length=200)
    check_in: date
    check_out: date
    description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("체크아웃은 체크인 다음 날 이후여야 합니다.")
        return self


class Activity(Model):
    id: str = Field(default_factory=lambda: str(uuid4()), max_length=100)
    day: date
    start: time
    end: time
    title: str = Field(min_length=1, max_length=200)
    area: str = Field(min_length=1, max_length=200)
    kind: Literal["sight", "meal", "transit", "rest"] = "sight"
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_times(self):
        if self.start.tzinfo or self.end.tzinfo or self.end <= self.start:
            raise ValueError("같은 날의 현지 시간으로 시작·종료 시간을 입력하세요.")
        return self


class Trip(Model):
    id: str
    version: int = 0
    flight: Flight | None = None
    hotel: Hotel | None = None
    activities: list[Activity] = Field(default_factory=list, max_length=500)

    @property
    def stage(self):
        if not self.flight:
            return "flight"
        if not self.hotel:
            return "hotel"
        if not self.activities:
            return "itinerary"
        return "restaurants"

    def set_flight(self, flight: Flight):
        if self.flight != flight:
            self.flight = flight
            self.hotel = None
            self.activities = []

    def set_hotel(self, hotel: Hotel):
        if not self.flight:
            raise ValueError("항공권을 먼저 확정하세요.")
        if not (self.flight.arrival_date <= hotel.check_in < hotel.check_out
                <= self.flight.departure_date):
            raise ValueError("숙박 날짜는 현지 도착일과 출발일 사이여야 합니다.")
        if self.hotel != hotel:
            self.hotel = hotel
            self.activities = []

    def set_activities(self, activities: list[Activity]):
        if not self.flight or not self.hotel:
            raise ValueError("항공권과 호텔을 먼저 확정하세요.")
        ordered = sorted(activities, key=lambda item: (item.day, item.start))
        if len({item.id for item in ordered}) != len(ordered):
            raise ValueError("일정 ID가 중복되었습니다.")
        arrival = datetime.combine(self.flight.arrival_date, self.flight.arrival_time)
        departure = datetime.combine(self.flight.departure_date, self.flight.departure_time)
        previous_end = arrival
        for item in ordered:
            start = datetime.combine(item.day, item.start)
            end = datetime.combine(item.day, item.end)
            if start < arrival or end > departure:
                raise ValueError("일정은 현지 도착 시간과 출발 시간 사이여야 합니다.")
            if start < previous_end:
                raise ValueError("일정 시간이 겹칩니다. 이동 시간도 확보하세요.")
            previous_end = end
        self.activities = ordered
