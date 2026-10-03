"""Review timing. Work time is the sum of unpaused intervals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class SessionError(ValueError):
    """A timer event repeats an id or arrives in an impossible order."""


_REVIEW = {"review_started", "review_paused", "review_resumed", "review_finished"}
_PROCESSING = {"processing_started", "processing_finished"}


@dataclass(frozen=True)
class SessionEvent:
    event_id: str
    event_type: str
    at: datetime


class ReviewSession:
    def __init__(self, replay: bool = False) -> None:
        self.replay = replay
        self._events: list[SessionEvent] = []
        self._ids: set[str] = set()
        self._review_open: datetime | None = None
        self._processing_open: datetime | None = None
        self._review_state = "idle"
        self._work_seconds = 0
        self._ai_seconds = 0
        self._started: datetime | None = None
        self._finished: datetime | None = None

    def record(self, event_id: str, event_type: str, at: datetime) -> None:
        if event_id in self._ids:
            raise SessionError(f"Duplicate event: {event_id}")
        if event_type not in _REVIEW and event_type not in _PROCESSING:
            raise SessionError(f"Unknown event type: {event_type}")
        if self._events and at < self._events[-1].at:
            raise SessionError("Event time moves backward.")
        self._apply(event_type, at)
        self._ids.add(event_id)
        self._events.append(SessionEvent(event_id, event_type, at))

    def events(self) -> tuple[SessionEvent, ...]:
        return tuple(self._events)

    def work_seconds(self) -> int:
        return self._work_seconds

    def ai_processing_seconds(self) -> int:
        return self._ai_seconds

    def elapsed_seconds(self) -> int | None:
        if self._started is None or self._finished is None:
            return None
        return _seconds(self._started, self._finished)

    def _apply(self, event_type: str, at: datetime) -> None:
        if event_type == "review_started":
            if self._review_state != "idle":
                raise SessionError("Review already started.")
            self._review_state = "running"
            self._review_open = at
            self._started = at
        elif event_type == "review_paused":
            if self._review_state != "running" or self._review_open is None:
                raise SessionError("Review is not running.")
            self._work_seconds += _seconds(self._review_open, at)
            self._review_open = None
            self._review_state = "paused"
        elif event_type == "review_resumed":
            if self._review_state != "paused":
                raise SessionError("Review is not paused.")
            self._review_state = "running"
            self._review_open = at
        elif event_type == "review_finished":
            if self._review_state == "running" and self._review_open is not None:
                self._work_seconds += _seconds(self._review_open, at)
                self._review_open = None
            elif self._review_state != "paused":
                raise SessionError("Review is not running.")
            self._review_state = "finished"
            self._finished = at
        elif event_type == "processing_started":
            if self._processing_open is not None:
                raise SessionError("Processing is already running.")
            self._processing_open = at
        else:
            if self._processing_open is None:
                raise SessionError("Processing has not started.")
            self._ai_seconds += _seconds(self._processing_open, at)
            self._processing_open = None


def _seconds(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds())
