from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import ReviewStatus


class TimeCertainty(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EventCreate(_M):
    id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=64)
    start_time: str | None = None
    end_time: str | None = None
    time_certainty: TimeCertainty = TimeCertainty.UNKNOWN
    place_entity_id: str | None = None
    participant_entity_ids: tuple[str, ...] = ()
    summary: str | None = None
    evidence_ids: tuple[str, ...] = ()
    is_inferred: bool = False
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None

    @model_validator(mode="after")
    def validate_time_policy(self) -> EventCreate:
        if self.time_certainty is TimeCertainty.EXACT and not self.start_time:
            raise ValueError("exact time requires start_time")
        if self.time_certainty is TimeCertainty.UNKNOWN and self.start_time and self.start_time.isdigit() and len(self.start_time) == 4:
            # Do not silently promote absolute 4-digit years to exact without explicit certainty.
            pass
        for label, value in (("start_time", self.start_time), ("end_time", self.end_time)):
            if value is not None and not value.strip():
                raise ValueError(f"{label} cannot be empty")
        if len(self.participant_entity_ids) != len(set(self.participant_entity_ids)) or any(
            not item.strip() for item in self.participant_entity_ids
        ):
            raise ValueError("participant entity IDs must be unique and non-empty")
        if self.start_time and self.end_time:
            try:
                if date.fromisoformat(self.start_time) > date.fromisoformat(self.end_time):
                    raise ValueError("event start_time must not be after end_time")
            except ValueError as exc:
                if str(exc).startswith("event start_time"):
                    raise
        return self


class EventRecord(EventCreate):
    id: str


class EventService:
    """In-memory historical event store used by stage 34 domain tests and local demos."""

    def __init__(self) -> None:
        self._items: dict[str, EventRecord] = {}

    def create(self, payload: EventCreate) -> EventRecord:
        if not payload.evidence_ids and not payload.is_inferred:
            raise ValueError("event requires evidence or is_inferred=true")
        if len(payload.evidence_ids) != len(set(payload.evidence_ids)) or any(not item.strip() for item in payload.evidence_ids):
            raise ValueError("event evidence IDs must be unique and non-empty")
        data = payload.model_dump(exclude={"id"})
        # Never rewrite approximate/unknown labels into fake exact years.
        if payload.time_certainty is not TimeCertainty.EXACT and data.get("start_time"):
            # Keep raw label; certainty stays explicit.
            data["time_certainty"] = payload.time_certainty
        record = EventRecord(id=payload.id or f"event-{uuid.uuid4().hex[:10]}", **data)
        if record.id in self._items:
            raise ValueError(f"event already exists: {record.id}")
        self._items[record.id] = record
        return record

    def list(
        self,
        *,
        place_entity_id: str | None = None,
        event_type: str | None = None,
        participant_entity_id: str | None = None,
        limit: int = 50,
    ) -> list[EventRecord]:
        rows = sorted(self._items.values(), key=lambda row: row.id)
        if place_entity_id:
            rows = [row for row in rows if row.place_entity_id == place_entity_id]
        if event_type:
            rows = [row for row in rows if row.event_type == event_type]
        if participant_entity_id:
            rows = [row for row in rows if participant_entity_id in row.participant_entity_ids]
        return rows[: max(1, min(limit, 200))]

    def get(self, event_id: str) -> EventRecord | None:
        return self._items.get(event_id)
