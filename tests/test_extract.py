import hashlib
from datetime import date
from pathlib import Path

import pytest

from transferlens.config import load_settings
from transferlens.extract.bedrock import extract_fields
from transferlens.extract.pipeline import ExtractionUnavailable, LiveClients, run_extraction
from transferlens.extract.textract import ExtractionError, signature_state, wait_for_analysis
from transferlens.policy import load_policy
from transferlens.review import evaluate
from transferlens.signatures import ABSENT, DETECTED, NEEDS_CONFIRMATION

ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides: str):
    env = {"TRANSFERLENS_PROJECT_ROOT": str(ROOT), "TRANSFERLENS_DATA_DIR": str(ROOT / ".local-data")}
    env.update(overrides)
    return load_settings(env)


def test_local_mode_does_not_call_extraction() -> None:
    with pytest.raises(ExtractionUnavailable, match="local mode"):
        run_extraction(_settings(), "TR-2026-001", {"statement": {}})


def test_default_profile_is_refused() -> None:
    settings = _settings(
        TRANSFERLENS_RUNTIME="aws",
        TRANSFERLENS_BUCKET="b",
        TRANSFERLENS_TABLE="t",
        AWS_PROFILE="default",
    )
    with pytest.raises(ExtractionUnavailable, match="personal default profile"):
        run_extraction(settings, "TR-2026-001", {"statement": {"data": b"%PDF-1.4", "sha256": "abc"}})


def test_wrong_account_stops_before_upload() -> None:
    settings = _settings(TRANSFERLENS_RUNTIME="aws", TRANSFERLENS_BUCKET="case-bucket", TRANSFERLENS_TABLE="t", AWS_PROFILE="hackathon")
    textract = _Textract()
    clients = _clients("235494815973", textract)
    with pytest.raises(ExtractionUnavailable, match="does not match"):
        run_extraction(settings, "TR-2026-001", _pdf_packet(), clients=clients)
    assert textract.locations == []
    assert clients.objects.keys == []


def test_live_extraction_stores_the_pdf_and_reuses_the_artifact() -> None:
    settings = _settings(
        TRANSFERLENS_RUNTIME="aws",
        TRANSFERLENS_BUCKET="case-bucket",
        TRANSFERLENS_TABLE="t",
        AWS_PROFILE="",
    )
    textract = _Textract()
    clients = _clients("884025082158", textract)
    first = run_extraction(settings, "TR-2026-001", _pdf_packet(), run_id="run-1", clients=clients)
    assert first.replay is False
    assert first.claims[0].value == "78451239"
    assert first.signatures[0].state == "signature mark detected"
    assert clients.objects.keys[0].startswith("cases/TR-2026-001/documents/statement/")
    assert "cases/TR-2026-001/runs/run-1/extraction.json" in clients.objects.keys
    assert clients.metadata.items[("CASE#TR-2026-001", "RUN#run-1")]["status"] == "extracted"
    assert textract.locations == [{"Bucket": "case-bucket", "Name": clients.objects.keys[0]}]

    second = run_extraction(settings, "TR-2026-001", _pdf_packet(), run_id="run-1", clients=clients)
    assert second.claims[0].value == "78451239"
    assert len(textract.locations) == 1


def test_replay_output_is_checked_by_the_rules() -> None:
    settings = _settings(TRANSFERLENS_RUNTIME="replay")
    extracted = run_extraction(settings, "TR-2026-001", {"statement": {}})
    assert extracted.replay is True
    policy = load_policy(ROOT / "policy" / "northstar_demo_policy.json")
    results = {
        item.rule_id: item.status
        for item in evaluate(
            policy,
            date(2026, 9, 1),
            extracted.claims,
            extracted.blocks,
            extracted.signatures,
            frozenset(policy["required_document_roles"]),
        )
    }
    assert results["accounts.source_agreement"] == "pass"
    assert results["statement.not_in_future"] == "fail"


def test_textract_paginates_and_keeps_failures() -> None:
    pages = [
        {"JobStatus": "IN_PROGRESS"},
        {"JobStatus": "SUCCEEDED", "Blocks": [{"Id": "a", "BlockType": "LINE", "Text": "one", "Page": 1}], "NextToken": "n"},
        {"JobStatus": "SUCCEEDED", "Blocks": [{"Id": "b", "BlockType": "LINE", "Text": "two", "Page": 2}]},
    ]

    class Client:
        def get_document_analysis(self, **kwargs):
            return pages.pop(0)

    blocks, partial = wait_for_analysis(Client(), "job-1", sleep=lambda _seconds: None)
    assert partial is False
    assert [block["Id"] for block in blocks] == ["a", "b"]

    class Failed:
        def get_document_analysis(self, **kwargs):
            return {"JobStatus": "FAILED", "StatusMessage": "bad pdf"}

    with pytest.raises(ExtractionError, match="bad pdf"):
        wait_for_analysis(Failed(), "job-2")


def test_signature_states() -> None:
    assert signature_state([], False) == ABSENT
    assert signature_state([{"BlockType": "SIGNATURE", "Confidence": 90}], False) == DETECTED
    assert signature_state([{"BlockType": "SIGNATURE"}], False) == NEEDS_CONFIRMATION
    assert signature_state([{"BlockType": "SIGNATURE", "Confidence": 99}], True) == NEEDS_CONFIRMATION


def test_bedrock_requires_the_tool_result() -> None:
    class Client:
        def converse(self, **kwargs):
            assert kwargs["toolConfig"]["toolChoice"]["tool"]["name"] == "record_fields"
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "record_fields",
                                    "input": {
                                        "fields": [
                                            {
                                                "field": "source_account_number",
                                                "value": "78451239",
                                                "page": 1,
                                                "source_block_ids": ["stmt-1"],
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    }
                }
            }

    from transferlens.evidence import TextBlock

    claims = extract_fields(Client(), "us.amazon.nova-pro-v1:0", "statement", "statement", (TextBlock("stmt-1", "statement", 1, "78451239"),))
    assert claims[0].value == "78451239"
    assert claims[0].source_block_ids == ("stmt-1",)

    class Empty:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [{"text": "I guessed the account."}]}}}

    with pytest.raises(ExtractionError, match="record_fields"):
        extract_fields(Empty(), "model", "statement", "statement", (TextBlock("stmt-1", "statement", 1, "78451239"),))


def _pdf_packet() -> dict:
    data = b"%PDF-1.4\n" + (b"0" * 120)
    return {"statement": {"filename": "statement.pdf", "data": data, "sha256": hashlib.sha256(data).hexdigest()}}


def _clients(account: str, textract: "_Textract") -> LiveClients:
    return LiveClients(_Sts(account), _Objects(), textract, _Bedrock(), _Meta())


class _Sts:
    def __init__(self, account: str) -> None:
        self._account = account

    def get_caller_identity(self) -> dict:
        return {"Account": self._account}


class _Objects:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put_new(self, key: str, data: bytes, content_type: str):
        self.store[key] = data
        return key

    def exists(self, key: str) -> bool:
        return key in self.store

    def get(self, key: str) -> bytes:
        return self.store[key]

    @property
    def keys(self) -> list[str]:
        return list(self.store)


class _Meta:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def put_new(self, item: dict):
        self.items[(item["pk"], item["sk"])] = dict(item)


class _Textract:
    def __init__(self) -> None:
        self.locations: list[dict] = []

    def start_document_analysis(self, **kwargs):
        self.locations.append(kwargs["DocumentLocation"]["S3Object"])
        return {"JobId": "job-1"}

    def get_document_analysis(self, **kwargs):
        return {
            "JobStatus": "SUCCEEDED",
            "Blocks": [
                {"Id": "line-1", "BlockType": "LINE", "Text": "Account 78451239", "Page": 1},
                {"Id": "sig-1", "BlockType": "SIGNATURE", "Confidence": 99, "Page": 2},
            ],
        }


class _Bedrock:
    def converse(self, **kwargs):
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "record_fields",
                                "input": {
                                    "fields": [
                                        {
                                            "field": "source_account_number",
                                            "value": "78451239",
                                            "page": 1,
                                            "source_block_ids": ["line-1"],
                                        }
                                    ]
                                },
                            }
                        }
                    ]
                }
            }
        }
