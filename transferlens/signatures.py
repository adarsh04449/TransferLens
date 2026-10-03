"""Signature states from a detector. A failed or unclear detection does not pass."""

from __future__ import annotations

from dataclasses import dataclass

DETECTED = "signature mark detected"
ABSENT = "no mark detected"
NEEDS_CONFIRMATION = "needs confirmation"


@dataclass(frozen=True)
class SignatureObservation:
    role: str
    document_id: str
    page: int
    state: str
    block_id: str | None = None


def evaluate_signatures(
    observations: tuple[SignatureObservation, ...] | list[SignatureObservation],
    required_roles: tuple[str, ...] | list[str],
    present_roles: frozenset[str],
) -> tuple[str, str]:
    """Return a rule status and an explanation for the required signature roles."""

    by_role = {item.role: item for item in observations}
    statuses: list[str] = []
    notes: list[str] = []
    for role in required_roles:
        if role not in present_roles:
            statuses.append("unknown")
            notes.append(f"{role} is not in the packet.")
            continue
        observation = by_role.get(role)
        if observation is None:
            statuses.append("unknown")
            notes.append(f"{role} has no signature result.")
            continue
        if observation.state == DETECTED:
            statuses.append("pass")
            notes.append(f"{role}: {DETECTED}.")
        elif observation.state == ABSENT:
            statuses.append("fail")
            notes.append(f"{role}: {ABSENT}.")
        elif observation.state == NEEDS_CONFIRMATION:
            statuses.append("needs_confirmation")
            notes.append(f"{role}: {NEEDS_CONFIRMATION}.")
        else:
            statuses.append("unknown")
            notes.append(f"{role} has an unrecognized signature result.")
    return _worst(statuses), " ".join(notes)


def _worst(statuses: list[str]) -> str:
    for status in ("fail", "unknown", "needs_confirmation", "pass"):
        if status in statuses:
            return status
    return "unknown"
