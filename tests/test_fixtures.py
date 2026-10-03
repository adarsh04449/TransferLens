import ast
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from transferlens.demo_packets import ROLES, DemoPacketError, load_demo_catalog
from transferlens.policy import load_policy
from transferlens.scoring.answer_key import AnswerKeyError, load_answer_key, load_answer_keys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "policy" / "northstar_demo_policy.json"
TEMPLATE = ROOT / "benchmark" / "manual_baseline_template.csv"
SCHEMA = ROOT / "benchmark" / "manual_baseline_schema.json"


def test_clean_packet_pdfs_match_the_catalog() -> None:
    catalog = load_demo_catalog(ROOT)
    packet = catalog.packet("TR-2026-001")
    assert packet.label == "clean"
    assert packet.reference_date == date(2026, 9, 1)
    assert catalog.not_supplied == ("defective",)
    assert [item.role for item in packet.documents] == list(ROLES)
    assert [item.pages for item in packet.documents] == [4, 2, 2, 3]
    for item in packet.documents:
        data = item.read_bytes()
        assert data.startswith(b"%PDF-")
        assert len(data) > 1000


def test_demo_catalog_has_no_answer_key_fields() -> None:
    raw = json.loads((ROOT / "fixtures" / "demo" / "catalog.json").read_text(encoding="utf-8"))
    text = json.dumps(raw)
    for secret in ("78451239", "55678901", "John", "planted_defects", "answer_key"):
        assert secret not in text
    policy = load_policy(POLICY)
    assert list(ROLES) == policy["required_document_roles"]


def test_answer_key_stays_separate_and_matches_the_clean_packet() -> None:
    keys = load_answer_keys(ROOT)
    key = keys["TR-2026-001"]
    packet = load_demo_catalog(ROOT).packet("TR-2026-001")
    assert key["use"] == "tests_and_benchmark_scoring_only"
    assert key["planted_defects"] == []
    assert key["expected"]["packet_ready"] is False
    assert key["expected"]["statement_is_after_reference_date"] is True
    assert key["expected"]["owner_name_comparison"] == "needs_confirmation"
    assert key["expected"]["source_account_numbers_agree"] is True
    assert key["expected"]["signatures_present_on_required_documents"] is True
    for document in packet.documents:
        assert key["documents"][document.role]["sha256"] == document.sha256
    key_path = ROOT / "fixtures" / "answer_keys" / "TR-2026-001.json"
    assert "fixtures/demo" not in str(key_path.relative_to(ROOT))
    assert not str(key_path).startswith(str(ROOT / "fixtures" / "demo"))


def test_application_code_does_not_reference_the_answer_key() -> None:
    allowed = ROOT / "transferlens" / "scoring" / "answer_key.py"
    offenders: list[str] = []
    for path in (ROOT / "transferlens").rglob("*.py"):
        if path == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "answer_key" in node.module:
                offenders.append(f"{path}:{node.lineno}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "answer_key" in node.value or "answer_keys" in node.value:
                    offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


def test_manual_baseline_template_is_header_only() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    expected = [column["name"] for column in schema["columns"]]
    with TEMPLATE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows == [expected]
    assert "manual" in schema["columns"][2]["allowed"]
    template_text = TEMPLATE.read_text(encoding="utf-8")
    for example in ("12", "4", "67", "720"):
        assert example not in template_text.split(",")


def test_answer_key_rejects_a_disagreement(tmp_path: Path) -> None:
    source = ROOT / "fixtures" / "answer_keys" / "TR-2026-001.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["expected"]["source_account_numbers_agree"] = False
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AnswerKeyError, match="source account"):
        load_answer_key(path)


def test_missing_demo_catalog_is_reported(tmp_path: Path) -> None:
    with pytest.raises(DemoPacketError, match="not found"):
        load_demo_catalog(tmp_path)
