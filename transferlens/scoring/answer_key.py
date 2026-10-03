"""Load ground truth for tests and benchmark scoring.

Textract, Bedrock, and extraction must not import this module or read these files.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from transferlens.demo_packets import ROLES


class AnswerKeyError(ValueError):
    """An answer key is missing a field scoring needs, or it disagrees with itself."""


def answer_key_dir(root: Path | None = None) -> Path:
    base = Path(__file__).resolve().parents[2] if root is None else root
    return base / "fixtures" / "answer_keys"


def load_answer_keys(root: Path | None = None) -> dict[str, dict]:
    directory = answer_key_dir(root)
    if not directory.is_dir():
        raise AnswerKeyError(f"Answer key directory was not found: {directory}")
    loaded: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        document = load_answer_key(path)
        packet_id = document["packet_id"]
        if packet_id in loaded:
            raise AnswerKeyError(f"Duplicate answer key for {packet_id}.")
        loaded[packet_id] = document
    if not loaded:
        raise AnswerKeyError(f"No answer keys were found in {directory}.")
    return loaded


def load_answer_key(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AnswerKeyError(f"Answer key was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AnswerKeyError(f"Answer key is not valid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise AnswerKeyError("Answer key must contain a JSON object.")
    if document.get("use") != "tests_and_benchmark_scoring_only":
        raise AnswerKeyError("Answer key use must be tests_and_benchmark_scoring_only.")
    for field in ("packet_id", "demo_reference_date", "documents", "planted_defects", "expected"):
        if field not in document:
            raise AnswerKeyError(f"Answer key is missing {field}.")
    documents = document["documents"]
    if tuple(documents) != ROLES:
        raise AnswerKeyError("Answer key documents must follow the four demo roles.")
    reference = date.fromisoformat(document["demo_reference_date"])
    statement_date = date.fromisoformat(documents["statement"]["fields"]["statement_date"])
    expected = document["expected"]
    if expected["statement_date"] != documents["statement"]["fields"]["statement_date"]:
        raise AnswerKeyError("Expected statement date does not match the statement field.")
    if expected["statement_is_after_reference_date"] != (statement_date > reference):
        raise AnswerKeyError("Statement date comparison does not match the recorded dates.")
    _require_agreement(
        expected["source_account_numbers_agree"],
        [
            documents["statement"]["fields"]["source_account_number"],
            documents["client_authorization"]["fields"]["source_account_number"],
            documents["northstar_transfer_form"]["fields"]["source_account_number"],
        ],
        "source account",
    )
    _require_agreement(
        expected["receiving_account_numbers_agree"],
        [
            documents["receiving_account_record"]["fields"]["receiving_account_number"],
            documents["client_authorization"]["fields"]["receiving_account_number"],
            documents["northstar_transfer_form"]["fields"]["receiving_account_number"],
        ],
        "receiving account",
    )
    if not isinstance(document["planted_defects"], list):
        raise AnswerKeyError("planted_defects must be a list.")
    return document


def _require_agreement(should_agree: bool, values: list[str], label: str) -> None:
    agrees = len(set(values)) == 1 and all(values)
    if agrees != should_agree:
        raise AnswerKeyError(f"{label} agreement does not match the recorded numbers.")
