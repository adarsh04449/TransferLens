from datetime import date
from pathlib import Path

import pytest

from transferlens.config import load_settings
from transferlens.extract.bedrock import extract_fields
from transferlens.extract.pipeline import ExtractionUnavailable, run_extraction
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
    settings = _settings(TRANSFERLENS_RUNTIME="aws", TRANSFERLENS_BUCKET="b", TRANSFERLENS_TABLE="t")
    with pytest.raises(ExtractionUnavailable, match="workshop profile"):
        run_extraction(settings, "TR-2026-001", {"statement": {}})


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
