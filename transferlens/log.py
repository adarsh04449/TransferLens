"""Log helpers that keep document text and account numbers out of log records."""

from __future__ import annotations

import logging
import re

_DIGIT_RUN = re.compile(r"\d{6,}")
_AWS_KEY = re.compile(r"\b(ASIA|AKIA)[A-Z0-9]{8,}\b")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(aws_secret_access_key|aws_session_token|secret_access_key|session_token)"
    r"(\s*[=:]\s*)(\S+)"
)
_REDACTED_FIELDS = {
    "value",
    "text",
    "account_number",
    "source_account_number",
    "receiving_account_number",
    "owner_name",
    "bytes",
    "body",
}


def redact_text(message: str) -> str:
    cleaned = _AWS_KEY.sub("[redacted-key]", message)
    cleaned = _SECRET_ASSIGNMENT.sub(r"\1\2[redacted]", cleaned)
    return _DIGIT_RUN.sub("[redacted-number]", cleaned)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format first so numbers and mapping arguments are part of the text
        # that gets redacted. Clearing args stops the formatter from interpolating again.
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


def safe_fields(fields: dict[str, object]) -> dict[str, object]:
    """Return identifiers that are safe to log. Drop extracted values and names."""

    return {key: value for key, value in fields.items() if key not in _REDACTED_FIELDS}


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("transferlens")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
