"""Check that a claimed field is supported by text on that document version."""

from __future__ import annotations

from dataclasses import dataclass

from transferlens.normalize import (
    account_numbers_in_text,
    collapse,
    date_in_text,
    normalize_account,
    parse_date,
)

ACCOUNT_FIELDS = {"source_account_number", "receiving_account_number"}
NAME_FIELDS = {"owner_name", "account_registration"}
DATE_FIELDS = {"statement_date", "authorization_date", "date_signed"}
BOOL_FIELDS = {"full_transfer", "cash_transfer"}


@dataclass(frozen=True)
class TextBlock:
    block_id: str
    document_id: str
    page: int
    text: str


@dataclass(frozen=True)
class FieldClaim:
    field: str
    role: str
    value: str | None
    document_id: str
    page: int
    source_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedField:
    field: str
    role: str
    document_id: str
    page: int
    original: str | None
    normalized: str | None
    normalization: tuple[str, ...]
    status: str
    reason: str
    source_block_ids: tuple[str, ...]


def verify_claim(claim: FieldClaim, blocks: tuple[TextBlock, ...] | list[TextBlock]) -> VerifiedField:
    if claim.value is None or not claim.value.strip():
        return _result(claim, None, (), "missing", "The field has no value.")
    cited = _cited_blocks(claim, blocks)
    if cited is None:
        return _result(
            claim,
            None,
            (),
            "unsupported",
            "A cited text block is missing from this document version.",
        )
    text = "\n".join(block.text for block in cited)
    if claim.field in ACCOUNT_FIELDS:
        return _verify_account(claim, text)
    if claim.field in NAME_FIELDS:
        return _verify_name(claim, text)
    if claim.field in DATE_FIELDS:
        return _verify_date(claim, text)
    if claim.field in BOOL_FIELDS:
        return _verify_bool(claim, text)
    folded = collapse(claim.value)
    if folded and folded in collapse(text):
        return _result(claim, folded, ("case", "whitespace"), "supported", "The text contains the value.")
    return _result(claim, None, (), "unsupported", "The cited text does not contain the value.")


def _cited_blocks(claim: FieldClaim, blocks: tuple[TextBlock, ...] | list[TextBlock]) -> tuple[TextBlock, ...] | None:
    if not claim.source_block_ids:
        return None
    by_id = {
        block.block_id: block
        for block in blocks
        if block.document_id == claim.document_id
    }
    cited: list[TextBlock] = []
    for block_id in claim.source_block_ids:
        block = by_id.get(block_id)
        if block is None or block.page != claim.page:
            return None
        cited.append(block)
    return tuple(cited)


def _verify_account(claim: FieldClaim, text: str) -> VerifiedField:
    normalized, steps, status = normalize_account(claim.value or "")
    if status == "unknown":
        return _result(
            claim,
            None,
            steps,
            "unknown",
            "The account number is masked or incomplete. Missing digits are not inferred.",
        )
    if normalized not in account_numbers_in_text(text):
        return _result(
            claim,
            None,
            steps,
            "unsupported",
            "The cited text does not contain this account number.",
        )
    return _result(claim, normalized, steps, "supported", "The cited text contains this account number.")


def _verify_name(claim: FieldClaim, text: str) -> VerifiedField:
    folded = collapse(claim.value or "")
    if folded not in collapse(text):
        return _result(claim, None, (), "unsupported", "The cited text does not contain this name.")
    return _result(claim, folded, ("case", "whitespace"), "supported", "The cited text contains this name.")


def _verify_date(claim: FieldClaim, text: str) -> VerifiedField:
    parsed = parse_date(claim.value or "")
    if parsed is None:
        return _result(claim, None, (), "unknown", "The date could not be read.")
    if not date_in_text(parsed, text):
        return _result(claim, None, (), "unsupported", "The cited text does not contain this date.")
    return _result(claim, parsed.isoformat(), ("parse_date",), "supported", "The cited text contains this date.")


def _verify_bool(claim: FieldClaim, text: str) -> VerifiedField:
    flag = (claim.value or "").strip().casefold()
    if flag not in {"true", "false"}:
        return _result(claim, None, (), "unknown", "The instruction is not true or false.")
    if not _text_supports_bool(claim.field, flag, text):
        return _result(claim, None, (), "unsupported", "The cited text does not support this instruction.")
    return _result(claim, flag, (), "supported", "The cited text supports this instruction.")


def _text_supports_bool(field: str, flag: str, text: str) -> bool:
    folded = text.casefold()
    if field == "full_transfer":
        if flag == "true":
            return "full transfer" in folded
        return "partial transfer" in folded and "full transfer" not in folded
    if flag == "true":
        return "cash" in folded and ("transfer" in folded or "liquidat" in folded)
    return "in kind" in folded and "cash" not in folded


def _result(
    claim: FieldClaim,
    normalized: str | None,
    steps: tuple[str, ...],
    status: str,
    reason: str,
) -> VerifiedField:
    return VerifiedField(
        field=claim.field,
        role=claim.role,
        document_id=claim.document_id,
        page=claim.page,
        original=None if claim.value is None else claim.value,
        normalized=normalized,
        normalization=steps,
        status=status,
        reason=reason,
        source_block_ids=claim.source_block_ids,
    )
