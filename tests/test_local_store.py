from pathlib import Path

import pytest

from transferlens.storage.keys import (
    EvidenceOverwriteError,
    StorageError,
    case_pk,
    document_object_key,
    document_sk,
    event_sk,
)
from transferlens.storage.local import LocalMetadataStore, LocalObjectStore


def test_same_bytes_are_not_stored_twice(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    key = document_object_key("case-1", "statement-v1", "abc123")
    first = store.put_new(key, b"%PDF-1.4 demo", "application/pdf")
    second = store.put_new(key, b"%PDF-1.4 demo", "application/pdf")
    assert first.created is True
    assert second.created is False
    assert second.sha256 == first.sha256
    assert store.get(key) == b"%PDF-1.4 demo"


def test_different_bytes_cannot_replace_evidence(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    key = document_object_key("case-1", "statement-v1", "abc123")
    store.put_new(key, b"original", "application/pdf")
    with pytest.raises(EvidenceOverwriteError):
        store.put_new(key, b"changed", "application/pdf")
    assert store.get(key) == b"original"


def test_parent_path_segments_are_rejected(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    with pytest.raises(StorageError):
        store.put_new("../secret", b"nope", "application/pdf")


def test_duplicate_metadata_and_events_return_the_original(tmp_path: Path) -> None:
    store = LocalMetadataStore(tmp_path)
    case = {
        "pk": case_pk("case-1"),
        "sk": "META",
        "status": "open",
        "reference_date": "2026-09-01",
    }
    created = store.put_new(case)
    duplicate = store.put_new({**case, "status": "exported"})
    assert created.created is True
    assert duplicate.created is False
    assert duplicate.item["status"] == "open"

    event = {
        "pk": case_pk("case-1"),
        "sk": event_sk("review-started-1"),
        "event_type": "review_started",
    }
    assert store.put_new(event).created is True
    assert store.put_new(event).created is False
    events = store.query_pk(case_pk("case-1"), "EVENT#")
    assert len(events) == 1
    documents = store.query_pk(case_pk("case-1"), document_sk("statement-v1")[:4])
    assert documents == []
