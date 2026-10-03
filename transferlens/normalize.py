"""Normalization allowed by the demo policy. Masked numbers stay unknown."""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_MASKED = re.compile(r"(?i)masked|ending|\*|x{2,}|#")
_MONTH_DATE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})")
_ACCOUNT_TOKEN = re.compile(r"\d(?:[\d\s-]*\d)?")


def collapse(value: str) -> str:
    return " ".join(value.casefold().split())


def parse_date(value: str) -> date | None:
    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = _MONTH_DATE.fullmatch(text)
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).casefold())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None


def date_in_text(value: date, text: str) -> bool:
    month_name = next(name for name, number in _MONTHS.items() if number == value.month)
    patterns = (
        value.isoformat(),
        f"{month_name} {value.day}, {value.year}",
    )
    folded = text.casefold()
    return any(pattern in folded for pattern in patterns)


def normalize_account(value: str) -> tuple[str | None, tuple[str, ...], str]:
    """Return normalized digits, applied steps, and supported or unknown.

    A mask or a partial number returns no digits. Missing digits are not filled in.
    """

    if _MASKED.search(value):
        return None, (), "unknown"
    applied: list[str] = []
    cleaned = value
    if " " in cleaned:
        cleaned = cleaned.replace(" ", "")
        applied.append("strip_spaces")
    if "-" in cleaned:
        cleaned = cleaned.replace("-", "")
        applied.append("strip_hyphens")
    if not cleaned.isdigit() or len(cleaned) < 6:
        return None, tuple(applied), "unknown"
    return cleaned, tuple(applied), "supported"


def account_numbers_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for match in _ACCOUNT_TOKEN.finditer(text):
        digits = re.sub(r"[\s-]", "", match.group())
        if digits.isdigit() and len(digits) >= 6:
            found.add(digits)
    return found


def compare_names(left: str, right: str) -> str:
    """Return pass, needs_confirmation, or fail.

    Case and whitespace differences pass. A middle initial, suffix, or punctuation
    difference needs confirmation. Any other difference fails.
    """

    folded_left = collapse(left)
    folded_right = collapse(right)
    if folded_left == folded_right:
        return "pass"
    plain_left = _strip_punctuation(folded_left)
    plain_right = _strip_punctuation(folded_right)
    if plain_left == plain_right:
        return "needs_confirmation"
    if _compatible(_tokens(plain_left), _tokens(plain_right)):
        return "needs_confirmation"
    return "fail"


def _strip_punctuation(value: str) -> str:
    return "".join(character for character in value if character.isalnum() or character.isspace())


def _tokens(value: str) -> list[str]:
    return [token for token in value.split() if token]


def _is_suffix(token: str) -> bool:
    return token in _SUFFIXES


def _compatible(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False
    return _align(left, right) or _align(right, left)


def _align(shorter: list[str], longer: list[str]) -> bool:
    if len(shorter) > len(longer):
        return False
    index = 0
    used_variation = False
    for token in shorter:
        if index >= len(longer):
            return False
        other = longer[index]
        if token == other:
            index += 1
            continue
        if len(token) == 1 and other.startswith(token) and len(other) > 1:
            used_variation = True
            index += 1
            continue
        if _is_suffix(token) and _is_suffix(other):
            used_variation = True
            index += 1
            continue
        return False
    leftover = longer[index:]
    if leftover and not all(_is_suffix(token) for token in leftover):
        return False
    if leftover:
        used_variation = True
    return used_variation
