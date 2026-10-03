from datetime import date
from pathlib import Path

from transferlens.policy import load_policy
from transferlens.review import decide_export, findings_for_run
from transferlens.ui.packets import UploadError, accept_pdf, load_demo_packet
from transferlens.ui.preview import illustrative_results

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_illustrative_layout_blocks_export_for_the_demo_packet() -> None:
    policy = load_policy(ROOT / "policy" / "northstar_demo_policy.json")
    results = illustrative_results(policy, date(2026, 9, 1))
    by_id = {item.rule_id: item.status for item in results}
    assert by_id["accounts.source_agreement"] == "pass"
    assert by_id["registration.owner_agreement"] == "needs_confirmation"
    assert by_id["statement.not_in_future"] == "fail"
    assert by_id["authorization.signature_fields"] == "pass"
    decision = decide_export(findings_for_run("run-1", results), "run-1")
    assert decision.allowed is False


def test_demo_packet_loader_returns_four_pdfs() -> None:
    case_id, documents = load_demo_packet(ROOT)
    assert case_id == "TR-2026-001"
    assert set(documents) == {
        "statement",
        "receiving_account_record",
        "client_authorization",
        "northstar_transfer_form",
    }
    for document in documents.values():
        assert document["data"].startswith(b"%PDF-")


def test_upload_rejects_a_non_pdf() -> None:
    with pytest.raises(UploadError, match="PDF"):
        accept_pdf("notes.txt", b"hello")
