"""Load demo PDFs and accept reviewer uploads."""

from __future__ import annotations

import hashlib
from pathlib import Path

from transferlens.demo_packets import load_demo_catalog

MAX_BYTES = 10 * 1024 * 1024


class UploadError(ValueError):
    """An uploaded file cannot be stored as packet evidence."""


def load_demo_packet(root: Path | None = None) -> tuple[str, dict[str, dict]]:
    catalog = load_demo_catalog(root)
    packet = catalog.packets[0]
    documents = {}
    for item in packet.documents:
        data = item.read_bytes()
        documents[item.role] = {
            "filename": item.path.name,
            "data": data,
            "sha256": item.sha256,
        }
    return packet.packet_id, documents


def accept_pdf(filename: str, data: bytes) -> dict:
    if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        raise UploadError("Upload a PDF.")
    if len(data) > MAX_BYTES:
        raise UploadError("That PDF is larger than 10 MB.")
    if len(data) < 100:
        raise UploadError("That PDF is empty.")
    return {
        "filename": Path(filename).name,
        "data": data,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
