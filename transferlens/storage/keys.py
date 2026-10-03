"""Object keys and DynamoDB item keys. Evidence paths include the content hash."""

from __future__ import annotations


class StorageError(Exception):
    """A stored object or metadata record could not be written safely."""


class EvidenceOverwriteError(StorageError):
    """An existing evidence object would have been replaced by different bytes."""


def _segment(value: str, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise StorageError(f"{label} is not a single path segment.")
    return value


def case_pk(case_id: str) -> str:
    return f"CASE#{_segment(case_id, 'case_id')}"


def case_meta_sk() -> str:
    return "META"


def document_sk(document_id: str) -> str:
    return f"DOC#{_segment(document_id, 'document_id')}"


def run_sk(run_id: str) -> str:
    return f"RUN#{_segment(run_id, 'run_id')}"


def finding_sk(finding_id: str) -> str:
    return f"FINDING#{_segment(finding_id, 'finding_id')}"


def session_sk(session_id: str) -> str:
    return f"SESSION#{_segment(session_id, 'session_id')}"


def event_sk(event_id: str) -> str:
    return f"EVENT#{_segment(event_id, 'event_id')}"


def benchmark_pk(import_id: str) -> str:
    return f"BENCH#{_segment(import_id, 'import_id')}"


def benchmark_row_sk(row_id: str) -> str:
    return f"ROW#{_segment(row_id, 'row_id')}"


def document_object_key(case_id: str, document_id: str, content_hash: str) -> str:
    return (
        f"cases/{_segment(case_id, 'case_id')}/documents/"
        f"{_segment(document_id, 'document_id')}/"
        f"{_segment(content_hash, 'content_hash')}.pdf"
    )


def run_artifact_key(case_id: str, run_id: str, name: str) -> str:
    return (
        f"cases/{_segment(case_id, 'case_id')}/runs/"
        f"{_segment(run_id, 'run_id')}/{_segment(name, 'name')}"
    )


def packet_object_key(case_id: str, packet_id: str) -> str:
    return (
        f"cases/{_segment(case_id, 'case_id')}/packets/"
        f"{_segment(packet_id, 'packet_id')}.pdf"
    )
