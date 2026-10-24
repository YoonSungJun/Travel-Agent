import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from .domain import Trip


class ConflictError(Exception):
    pass


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, "
                       "version INTEGER NOT NULL, data TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            yield db

    def create(self):
        trip = Trip(id=str(uuid4()))
        with self.connect() as db:
            db.execute("INSERT INTO trips VALUES (?, ?, ?)",
                       (trip.id, trip.version, trip.model_dump_json()))
        return trip

    def get(self, trip_id: str):
        try:
            UUID(trip_id)
        except ValueError:
            raise KeyError("여행을 찾을 수 없습니다.") from None
        with self.connect() as db:
            row = db.execute("SELECT data FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise KeyError("여행을 찾을 수 없습니다.")
        return Trip.model_validate_json(row[0])

    def save(self, trip: Trip, expected_version: int):
        trip.version = expected_version + 1
        with self.connect() as db:
            cursor = db.execute("UPDATE trips SET version = ?, data = ? "
                                "WHERE id = ? AND version = ?",
                                (trip.version, trip.model_dump_json(), trip.id, expected_version))
            if cursor.rowcount != 1:
                raise ConflictError("다른 창에서 수정되었습니다. 새로고침 후 다시 시도하세요.")
        return trip
