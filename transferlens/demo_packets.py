"""Load supplied demo PDFs. This module does not read answer keys."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class DemoPacketError(ValueError):
    """The demo catalog or a supplied PDF is not usable."""


ROLES = (
    "statement",
    "receiving_account_record",
    "client_authorization",
    "northstar_transfer_form",
)

_PAGE = re.compile(rb"/Type\s*/Page(?!s)")


@dataclass(frozen=True)
class DemoDocument:
    role: str
    path: Path
    pages: int
    sha256: str

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


@dataclass(frozen=True)
class DemoPacket:
    packet_id: str
    label: str
    reference_date: date
    documents: tuple[DemoDocument, ...]

    def document(self, role: str) -> DemoDocument:
        for item in self.documents:
            if item.role == role:
                return item
        raise DemoPacketError(f"Packet {self.packet_id} has no {role} document.")


@dataclass(frozen=True)
class DemoCatalog:
    packets: tuple[DemoPacket, ...]
    not_supplied: tuple[str, ...]

    def packet(self, packet_id: str) -> DemoPacket:
        for item in self.packets:
            if item.packet_id == packet_id:
                return item
        raise DemoPacketError(f"Demo packet was not found: {packet_id}")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_demo_catalog(root: Path | None = None) -> DemoCatalog:
    base = repository_root() if root is None else root
    catalog_path = base / "fixtures" / "demo" / "catalog.json"
    try:
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DemoPacketError(f"Demo catalog was not found: {catalog_path}") from exc
    except json.JSONDecodeError as exc:
        raise DemoPacketError(f"Demo catalog is not valid JSON: {catalog_path}") from exc
    packets = tuple(
        _packet(base / "fixtures" / "demo", raw)
        for raw in document.get("packets", [])
    )
    if not packets:
        raise DemoPacketError("Demo catalog has no packets.")
    missing = tuple(
        item["label"]
        for item in document.get("not_supplied", [])
        if isinstance(item, dict) and item.get("label")
    )
    supplied = {packet.label for packet in packets}
    overlap = supplied.intersection(missing)
    if overlap:
        raise DemoPacketError(
            "A packet cannot be both supplied and missing: " + ", ".join(sorted(overlap))
        )
    return DemoCatalog(packets, missing)


def _packet(demo_root: Path, raw: dict) -> DemoPacket:
    label = raw["label"]
    documents = tuple(_document(demo_root / label, item) for item in raw["documents"])
    roles = tuple(item.role for item in documents)
    if roles != ROLES:
        raise DemoPacketError(
            f"Packet {raw['packet_id']} roles must be " + ", ".join(ROLES) + "."
        )
    return DemoPacket(
        packet_id=raw["packet_id"],
        label=label,
        reference_date=date.fromisoformat(raw["reference_date"]),
        documents=documents,
    )


def _document(packet_dir: Path, raw: dict) -> DemoDocument:
    path = packet_dir / raw["filename"]
    if not path.is_file():
        raise DemoPacketError(f"Demo PDF was not found: {path}")
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise DemoPacketError(f"Demo file is not a PDF: {path}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != raw["sha256"]:
        raise DemoPacketError(f"Demo PDF hash does not match the catalog: {path.name}")
    pages = len(_PAGE.findall(data))
    if pages != raw["pages"]:
        raise DemoPacketError(
            f"{path.name} has {pages} pages; the catalog says {raw['pages']}."
        )
    return DemoDocument(raw["role"], path, pages, digest)
