"""Compare manual baseline time with assisted review time.

Replay sessions and AI processing time are excluded. A missing or zero manual
baseline is not measured. This module does not read ground-truth files itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from transferlens.scoring.baseline import ManualRow


@dataclass(frozen=True)
class PacketExpectation:
    packet_ready: bool
    planted_defect_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssistedSession:
    packet_id: str
    work_seconds: int
    fields_edited: int
    defects_found: int
    marked_ready: bool
    replay: bool = False
    ai_processing_seconds: int = 0
    found_defect_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class MetricsSnapshot:
    packet_id: str
    sample_manual: int
    sample_assisted: int
    manual_work_seconds: float | None
    assisted_work_seconds: float | None
    reduction_pct: float | None
    manual_fields_edited: int | None
    assisted_fields_edited: int | None
    defects_found: int | None
    planted_found: int | None
    planted_total: int | None
    false_alerts: int | None
    readiness_correct: int | None
    readiness_total: int | None
    time_measured: bool


def completed_assisted_session(
    packet_id: str,
    layout: str,
    finished: bool,
    work_seconds: int,
    fields_edited: int,
    defects_found: int,
    marked_ready: bool,
    ai_processing_seconds: int = 0,
) -> AssistedSession | None:
    """Return a metrics row for a finished review. Replay and the illustrative layout stay out."""

    if not finished or not packet_id or layout in {"replay", "illustrative"}:
        return None
    return AssistedSession(
        packet_id=packet_id,
        work_seconds=work_seconds,
        fields_edited=fields_edited,
        defects_found=defects_found,
        marked_ready=marked_ready,
        replay=False,
        ai_processing_seconds=ai_processing_seconds,
    )


def reduction_pct(manual_work_seconds: float, assisted_work_seconds: float) -> float | None:
    if manual_work_seconds <= 0:
        return None
    return (manual_work_seconds - assisted_work_seconds) / manual_work_seconds * 100


def compare_packet(
    packet_id: str,
    manual: tuple[ManualRow, ...] | list[ManualRow],
    assisted: tuple[AssistedSession, ...] | list[AssistedSession],
    expectation: PacketExpectation | None = None,
) -> MetricsSnapshot:
    manual_rows = [
        row
        for row in manual
        if row.packet_id == packet_id and row.mode == "manual" and row.review_completed
    ]
    assisted_rows = [row for row in assisted if row.packet_id == packet_id and not row.replay]
    manual_time = median(row.work_seconds for row in manual_rows) if manual_rows else None
    assisted_time = median(row.work_seconds for row in assisted_rows) if assisted_rows else None
    measured = manual_time is not None and assisted_time is not None and manual_time > 0
    percent = reduction_pct(manual_time, assisted_time) if measured and manual_time is not None and assisted_time is not None else None
    planted_found, planted_total, false_alerts = _planted(assisted_rows, expectation)
    readiness_correct, readiness_total = _readiness(assisted_rows, expectation)
    return MetricsSnapshot(
        packet_id=packet_id,
        sample_manual=len(manual_rows),
        sample_assisted=len(assisted_rows),
        manual_work_seconds=None if manual_time is None else float(manual_time),
        assisted_work_seconds=None if assisted_time is None else float(assisted_time),
        reduction_pct=percent,
        manual_fields_edited=sum(row.fields_edited for row in manual_rows) if manual_rows else None,
        assisted_fields_edited=sum(row.fields_edited for row in assisted_rows) if assisted_rows else None,
        defects_found=sum(row.defects_found for row in assisted_rows) if assisted_rows else None,
        planted_found=planted_found,
        planted_total=planted_total,
        false_alerts=false_alerts,
        readiness_correct=readiness_correct,
        readiness_total=readiness_total,
        time_measured=measured,
    )


def _planted(
    assisted_rows: list[AssistedSession],
    expectation: PacketExpectation | None,
) -> tuple[int | None, int | None, int | None]:
    if expectation is None or not assisted_rows:
        return None, None, None
    if any(row.found_defect_ids is None for row in assisted_rows):
        return None, len(expectation.planted_defect_ids), None
    planted = set(expectation.planted_defect_ids)
    found: set[str] = set()
    extras: set[str] = set()
    for row in assisted_rows:
        for defect_id in row.found_defect_ids or ():
            if defect_id in planted:
                found.add(defect_id)
            else:
                extras.add(defect_id)
    return len(found), len(planted), len(extras)


def _readiness(
    assisted_rows: list[AssistedSession],
    expectation: PacketExpectation | None,
) -> tuple[int | None, int | None]:
    if expectation is None or not assisted_rows:
        return None, None
    correct = sum(1 for row in assisted_rows if row.marked_ready == expectation.packet_ready)
    return correct, len(assisted_rows)
