"""Six deterministic checks from the NorthStar demo policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from transferlens.evidence import VerifiedField
from transferlens.normalize import compare_names, parse_date
from transferlens.signatures import SignatureObservation, evaluate_signatures

BLOCKING = {"fail", "needs_confirmation", "unknown"}


@dataclass(frozen=True)
class ReviewInput:
    policy: dict
    reference_date: date
    present_roles: frozenset[str]
    fields: tuple[VerifiedField, ...]
    signatures: tuple[SignatureObservation, ...]


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    group_id: str
    policy_version: str
    status: str
    explanation: str
    values: tuple[tuple[str, str], ...]
    evidence_refs: tuple[tuple[str, str], ...]
    recommended_action: str

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING


def run_rules(review: ReviewInput, summary: str | None = None) -> tuple[CheckResult, ...]:
    """Run the policy groups in order. A summary cannot change a result."""

    del summary
    version = str(review.policy["version"])
    results: list[CheckResult] = []
    for group in review.policy["rule_groups"]:
        group_id = group["id"]
        if group_id == "documents.required_roles":
            results.extend(_required_roles(review, group, version))
        elif group_id == "accounts.source_agreement":
            results.append(_accounts(review, group, version))
        elif group_id == "accounts.receiving_agreement":
            results.append(_accounts(review, group, version))
        elif group_id == "registration.owner_agreement":
            results.append(_owners(review, group, version))
        elif group_id == "statement.age_window":
            results.extend(_statement_age(review, group, version))
        elif group_id == "authorization.completeness":
            results.extend(_authorization(review, group, version))
        else:
            raise ValueError(f"Unknown rule group: {group_id}")
    return tuple(results)


def _required_roles(review: ReviewInput, group: dict, version: str) -> list[CheckResult]:
    results = []
    for subcheck in group["subchecks"]:
        role = subcheck["role"]
        present = role in review.present_roles
        results.append(
            _check(
                subcheck["id"],
                group["id"],
                version,
                "pass" if present else "fail",
                f"{role} is present." if present else f"{role} is missing.",
                (("role", role),),
                (),
                "No action." if present else f"Upload the {role} document.",
            )
        )
    return results


def _accounts(review: ReviewInput, group: dict, version: str) -> CheckResult:
    field = group["field"]
    usable: list[VerifiedField] = []
    blocked: list[VerifiedField] = []
    for role in group["roles"]:
        if role not in review.present_roles:
            return _check(
                group["id"],
                group["id"],
                version,
                "unknown",
                f"{role} is missing, so {field} cannot be compared.",
                (("field", field), ("missing_role", role)),
                (),
                "Upload the missing document before comparing account numbers.",
            )
        matches = [item for item in review.fields if item.role == role and item.field == field]
        if not matches or matches[-1].status != "supported" or not matches[-1].normalized:
            chosen = matches[-1] if matches else None
            if chosen is not None:
                blocked.append(chosen)
            else:
                return _check(
                    group["id"],
                    group["id"],
                    version,
                    "unknown",
                    f"{role} has no verified {field}.",
                    (("field", field), ("role", role)),
                    (),
                    "Confirm the account number from the document. Do not fill in missing digits.",
                )
        else:
            usable.append(matches[-1])
    if blocked:
        return _check(
            group["id"],
            group["id"],
            version,
            "unknown",
            blocked[0].reason,
            tuple(("value", item.original or "") for item in blocked),
            _refs(blocked),
            "Confirm the account number from the document. Do not fill in missing digits.",
        )
    numbers = {item.normalized for item in usable}
    if len(numbers) == 1:
        return _check(
            group["id"],
            group["id"],
            version,
            "pass",
            f"{field} agrees.",
            tuple((item.role, item.normalized or "") for item in usable),
            _refs(usable),
            "No action.",
        )
    return _check(
        group["id"],
        group["id"],
        version,
        "fail",
        f"{field} does not agree.",
        tuple((item.role, item.normalized or "") for item in usable),
        _refs(usable),
        "Upload a corrected document so the account numbers agree.",
    )


def _owners(review: ReviewInput, group: dict, version: str) -> CheckResult:
    comparisons: list[str] = []
    values: list[tuple[str, str]] = []
    refs: list[VerifiedField] = []
    for field in group["fields"]:
        items = [
            item
            for item in review.fields
            if item.field == field and item.role in review.present_roles
        ]
        if len(items) < 2:
            return _check(
                group["id"],
                group["id"],
                version,
                "unknown",
                f"{field} is not verified on enough documents to compare.",
                (("field", field),),
                _refs(items),
                "Confirm the owner and registration from the documents.",
            )
        unverified = [item for item in items if item.status != "supported" or not item.normalized]
        if unverified:
            return _check(
                group["id"],
                group["id"],
                version,
                "unknown",
                unverified[0].reason,
                (("field", field),),
                _refs(items),
                "Confirm the owner and registration from the documents.",
            )
        refs.extend(items)
        for item in items:
            values.append((f"{item.role}.{field}", item.original or ""))
        for index, left in enumerate(items):
            for right in items[index + 1 :]:
                comparisons.append(compare_names(left.normalized or "", right.normalized or ""))
    status = _worst(comparisons)
    explanations = {
        "pass": "Owner and registration agree after case and whitespace normalization.",
        "needs_confirmation": "A middle initial, suffix, or punctuation difference needs reviewer confirmation.",
        "fail": "Owner or registration names do not match.",
        "unknown": "Owner and registration could not be compared.",
    }
    actions = {
        "pass": "No action.",
        "needs_confirmation": "A reviewer must confirm this name difference before it can pass.",
        "fail": "Upload a corrected document or record an override with a reason.",
        "unknown": "Confirm the owner and registration from the documents.",
    }
    return _check(
        group["id"],
        group["id"],
        version,
        status,
        explanations[status],
        tuple(values),
        _refs(refs),
        actions[status],
    )


def _statement_age(review: ReviewInput, group: dict, version: str) -> list[CheckResult]:
    statement = _one(review, "statement", "statement_date")
    results = []
    for subcheck in group["subchecks"]:
        check_id = subcheck["id"]
        if statement is None or statement.status != "supported" or statement.normalized is None:
            reason = "The statement date is not verified." if statement is None else statement.reason
            results.append(
                _check(
                    check_id,
                    group["id"],
                    version,
                    "unknown",
                    reason,
                    (),
                    _refs([statement] if statement else []),
                    "Confirm the statement date from the document.",
                )
            )
            continue
        parsed = parse_date(statement.normalized)
        if parsed is None:
            results.append(
                _check(
                    check_id,
                    group["id"],
                    version,
                    "unknown",
                    "The statement date is not verified.",
                    (("statement_date", statement.normalized),),
                    _refs([statement]),
                    "Confirm the statement date from the document.",
                )
            )
            continue
        age_days = (review.reference_date - parsed).days
        if check_id == "statement.not_in_future":
            future = parsed > review.reference_date
            results.append(
                _check(
                    check_id,
                    group["id"],
                    version,
                    "fail" if future else "pass",
                    (
                        f"The statement date {parsed.isoformat()} is after {review.reference_date.isoformat()}."
                        if future
                        else f"The statement date {parsed.isoformat()} is on or before the reference date."
                    ),
                    (("statement_date", parsed.isoformat()), ("reference_date", review.reference_date.isoformat())),
                    _refs([statement]),
                    "Upload a statement dated on or before the reference date." if future else "No action.",
                )
            )
        else:
            limit = int(subcheck["max_age_days"])
            stale = age_days > limit
            results.append(
                _check(
                    check_id,
                    group["id"],
                    version,
                    "fail" if stale else "pass",
                    (
                        f"The statement is {age_days} days before the reference date. The limit is {limit} days."
                        if stale
                        else f"The statement is within {limit} days of the reference date."
                    ),
                    (
                        ("statement_date", parsed.isoformat()),
                        ("age_days", str(age_days)),
                        ("max_age_days", str(limit)),
                    ),
                    _refs([statement]),
                    "Upload a statement within the age window." if stale else "No action.",
                )
            )
    return results


def _authorization(review: ReviewInput, group: dict, version: str) -> list[CheckResult]:
    results = []
    for subcheck in group["subchecks"]:
        check_id = subcheck["id"]
        if check_id == "authorization.full_transfer":
            results.append(_bool_check(review, group["id"], version, check_id, "full_transfer", True))
        elif check_id == "authorization.cash_instruction":
            results.append(_bool_check(review, group["id"], version, check_id, "cash_transfer", True))
        elif check_id == "authorization.required_dates":
            results.append(_dates(review, group["id"], version, check_id))
        elif check_id == "authorization.signature_fields":
            results.append(_signatures(review, group["id"], version, check_id))
        else:
            raise ValueError(f"Unknown authorization check: {check_id}")
    return results


def _bool_check(
    review: ReviewInput,
    group_id: str,
    version: str,
    rule_id: str,
    field: str,
    expected: bool,
) -> CheckResult:
    items = [item for item in review.fields if item.field == field and item.role in review.present_roles]
    if not items:
        return _check(
            rule_id,
            group_id,
            version,
            "unknown",
            f"{field} was not found.",
            (("field", field),),
            (),
            "Confirm the transfer instruction from the authorization.",
        )
    if any(item.status != "supported" or item.normalized is None for item in items):
        failed = next(item for item in items if item.status != "supported" or item.normalized is None)
        return _check(
            rule_id,
            group_id,
            version,
            "unknown",
            failed.reason,
            _pairs(items),
            _refs(items),
            "Confirm the transfer instruction from the authorization.",
        )
    flags = {item.normalized for item in items}
    expected_text = "true" if expected else "false"
    if flags == {expected_text}:
        return _check(
            rule_id,
            group_id,
            version,
            "pass",
            f"{field} is {expected_text}.",
            _pairs(items),
            _refs(items),
            "No action.",
        )
    return _check(
        rule_id,
        group_id,
        version,
        "fail",
        f"{field} is not {expected_text}.",
        _pairs(items),
        _refs(items),
        "Upload a corrected authorization for a full cash transfer.",
    )


def _dates(review: ReviewInput, group_id: str, version: str, rule_id: str) -> CheckResult:
    needed = ("authorization_date", "date_signed")
    items = []
    for field in needed:
        item = _one(review, "client_authorization", field)
        if item is None or item.status != "supported" or item.normalized is None:
            reason = "The authorization is missing a required date." if item is None else item.reason
            return _check(
                rule_id,
                group_id,
                version,
                "unknown",
                reason,
                (("field", field),),
                _refs([item] if item else []),
                "Confirm the authorization date and the signature date.",
            )
        items.append(item)
    return _check(
        rule_id,
        group_id,
        version,
        "pass",
        "The authorization date and signature date are present.",
        _pairs(items),
        _refs(items),
        "No action.",
    )


def _signatures(review: ReviewInput, group_id: str, version: str, rule_id: str) -> CheckResult:
    status, explanation = evaluate_signatures(
        review.signatures,
        tuple(review.policy["signature_documents"]),
        review.present_roles,
    )
    actions = {
        "pass": "No action.",
        "fail": "Upload a document with a signature mark in the required area.",
        "needs_confirmation": "A reviewer must confirm the signature mark before it can pass.",
        "unknown": "The signature check did not finish. Run it again before export.",
    }
    return _check(rule_id, group_id, version, status, explanation, (), (), actions[status])


def _one(review: ReviewInput, role: str, field: str) -> VerifiedField | None:
    matches = [item for item in review.fields if item.role == role and item.field == field]
    if not matches:
        return None
    return matches[-1]


def _pairs(items: list[VerifiedField]) -> tuple[tuple[str, str], ...]:
    return tuple((f"{item.role}.{item.field}", item.normalized or "") for item in items)


def _refs(items: list[VerifiedField]) -> tuple[tuple[str, str], ...]:
    refs = []
    for item in items:
        for block_id in item.source_block_ids:
            refs.append((item.document_id, block_id))
    return tuple(refs)


def _worst(statuses: list[str]) -> str:
    for status in ("fail", "unknown", "needs_confirmation", "pass"):
        if status in statuses:
            return status
    return "unknown"


def _check(
    rule_id: str,
    group_id: str,
    version: str,
    status: str,
    explanation: str,
    values: tuple[tuple[str, str], ...],
    evidence_refs: tuple[tuple[str, str], ...],
    action: str,
) -> CheckResult:
    return CheckResult(
        rule_id=rule_id,
        group_id=group_id,
        policy_version=version,
        status=status,
        explanation=explanation,
        values=values,
        evidence_refs=evidence_refs,
        recommended_action=action,
    )
