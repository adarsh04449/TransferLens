import logging

from transferlens.log import RedactingFilter, redact_text, safe_fields


def test_redact_text_hides_account_numbers_and_aws_keys() -> None:
    message = redact_text(
        "account 78451239 key ASIAEXAMPLEKEY123456 "
        "aws_session_token=IQoJsecret aws_secret_access_key=abc123secret"
    )
    assert "78451239" not in message
    assert "ASIAEXAMPLEKEY123456" not in message
    assert "IQoJsecret" not in message
    assert "abc123secret" not in message
    assert "[redacted-number]" in message
    assert "[redacted-key]" in message


def _record(msg: str, args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="transferlens",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_log_filter_redacts_string_arguments() -> None:
    record = _record("source account %s", ("78451239",))
    assert RedactingFilter().filter(record) is True
    assert record.getMessage() == "source account [redacted-number]"


def test_log_filter_redacts_numeric_arguments() -> None:
    record = _record("source account %s", (78451239,))
    assert RedactingFilter().filter(record) is True
    assert "78451239" not in record.getMessage()
    assert record.getMessage() == "source account [redacted-number]"


def test_log_filter_redacts_mapping_arguments() -> None:
    record = _record("source account %(account)s", ({"account": 78451239},))
    assert RedactingFilter().filter(record) is True
    assert "78451239" not in record.getMessage()
    assert record.args == ()


def test_safe_fields_drop_extracted_values() -> None:
    fields = safe_fields(
        {
            "case_id": "case-1",
            "source_account_number": "78451239",
            "owner_name": "Avery Quinn",
        }
    )
    assert fields == {"case_id": "case-1"}
