"""Import the manual stopwatch CSV. An empty sheet is zero sessions."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


class BaselineError(ValueError):
    """The manual baseline CSV does not match its schema."""


@dataclass(frozen=True)
class ManualRow:
    reviewer_id: str
    packet_id: str
    mode: str
    work_seconds: int
    fields_edited: int
    defects_found: int
    findings: str
    marked_ready: bool
    review_completed: bool


def load_manual_baseline(path: Path, schema_path: Path) -> tuple[ManualRow, ...]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    columns = schema["columns"]
    expected = [column["name"] for column in columns]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != expected:
        raise BaselineError("The baseline header does not match the schema.")
    loaded: list[ManualRow] = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(expected):
            raise BaselineError(f"Row {number} has {len(row)} columns.")
        raw = dict(zip(expected, row, strict=True))
        loaded.append(_row(number, raw, columns))
    return tuple(loaded)


def _row(number: int, raw: dict[str, str], columns: list[dict]) -> ManualRow:
    parsed: dict[str, object] = {}
    for column in columns:
        name = column["name"]
        value = raw[name].strip()
        if column.get("required") and value == "" and column["type"] != "string":
            raise BaselineError(f"Row {number} is missing {name}.")
        if column["type"] == "integer":
            parsed[name] = _integer(number, name, value, int(column.get("minimum", 0)))
        elif column["type"] == "boolean":
            parsed[name] = _boolean(number, name, value)
        else:
            allowed = column.get("allowed")
            if allowed is not None and value not in allowed:
                raise BaselineError(f"Row {number} has an invalid {name}.")
            parsed[name] = value
    return ManualRow(
        reviewer_id=str(parsed["reviewer_id"]),
        packet_id=str(parsed["packet_id"]),
        mode=str(parsed["mode"]),
        work_seconds=int(parsed["work_seconds"]),
        fields_edited=int(parsed["fields_edited"]),
        defects_found=int(parsed["defects_found"]),
        findings=str(parsed["findings"]),
        marked_ready=bool(parsed["marked_ready"]),
        review_completed=bool(parsed["review_completed"]),
    )


def _integer(number: int, name: str, value: str, minimum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise BaselineError(f"Row {number} has a non-integer {name}.") from exc
    if parsed < minimum:
        raise BaselineError(f"Row {number} has {name} below {minimum}.")
    return parsed


def _boolean(number: int, name: str, value: str) -> bool:
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    raise BaselineError(f"Row {number} has an invalid {name}.")
