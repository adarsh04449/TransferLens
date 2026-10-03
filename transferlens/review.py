"""Findings, overrides, and the export gate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from transferlens.evidence import FieldClaim, TextBlock, VerifiedField, verify_claim
from transferlens.rules import CheckResult, ReviewInput, run_rules
from transferlens.signatures import SignatureObservation


class ReviewError(ValueError):
    """A review action is missing information the audit trail requires."""


@dataclass(frozen=True)
class Finding:
    finding_id: str
    run_id: str
    result: CheckResult
    disposition: str = "unresolved"
    override_reason: str | None = None


@dataclass(frozen=True)
class ExportDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate(
    policy: dict,
    reference_date: date,
    claims: tuple[FieldClaim, ...] | list[FieldClaim],
    blocks: tuple[TextBlock, ...] | list[TextBlock],
    signatures: tuple[SignatureObservation, ...] | list[SignatureObservation],
    present_roles: frozenset[str],
    summary: str | None = None,
) -> tuple[CheckResult, ...]:
    verified = tuple(verify_claim(claim, blocks) for claim in claims)
    return run_rules(
        ReviewInput(policy, reference_date, present_roles, verified, tuple(signatures)),
        summary=summary,
    )


def findings_for_run(run_id: str, results: tuple[CheckResult, ...] | list[CheckResult]) -> tuple[Finding, ...]:
    return tuple(
        Finding(finding_id=f"{run_id}:{result.rule_id}", run_id=run_id, result=result)
        for result in results
    )


def override_finding(finding: Finding, reason: str) -> Finding:
    if finding.disposition == "superseded":
        raise ReviewError("A superseded finding cannot be overridden.")
    if not finding.result.blocking:
        raise ReviewError("A passing check does not need an override.")
    if not reason or not reason.strip():
        raise ReviewError("An override needs a recorded reason.")
    return replace(finding, disposition="overridden", override_reason=reason.strip())


def supersede(findings: tuple[Finding, ...] | list[Finding]) -> tuple[Finding, ...]:
    """Mark a finished run superseded. Its approvals do not carry into the next run."""

    return tuple(replace(finding, disposition="superseded") for finding in findings)


def decide_export(
    findings: tuple[Finding, ...] | list[Finding],
    run_id: str,
    processing_failed: bool = False,
) -> ExportDecision:
    reasons: list[str] = []
    if processing_failed:
        reasons.append("Processing failed.")
    owned = [finding for finding in findings if finding.run_id == run_id]
    if not owned:
        reasons.append("This run has no review results.")
    elif all(finding.disposition == "superseded" for finding in owned):
        reasons.append("This run was superseded by a later review.")
    else:
        for finding in owned:
            if finding.disposition in {"overridden", "superseded"}:
                continue
            if finding.result.blocking:
                reasons.append(f"{finding.result.rule_id}: {finding.result.explanation}")
    return ExportDecision(allowed=not reasons, reasons=tuple(reasons))


def verified_fields(
    claims: tuple[FieldClaim, ...] | list[FieldClaim],
    blocks: tuple[TextBlock, ...] | list[TextBlock],
) -> tuple[VerifiedField, ...]:
    return tuple(verify_claim(claim, blocks) for claim in claims)
