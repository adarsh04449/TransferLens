"""Storage contracts shared by the local directory and AWS implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int
    content_type: str
    created: bool


@dataclass(frozen=True)
class StoredItem:
    item: dict[str, Any]
    created: bool


class ObjectStore(Protocol):
    def put_new(self, key: str, data: bytes, content_type: str) -> StoredObject:
        """Store bytes. Identical bytes at the same key are returned unchanged."""

    def get(self, key: str) -> bytes:
        """Return the stored bytes for a key."""

    def exists(self, key: str) -> bool:
        """Report whether a key already has bytes."""


class MetadataStore(Protocol):
    def put_new(self, item: Mapping[str, Any]) -> StoredItem:
        """Insert an item. An existing primary key is returned unchanged."""

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        """Return one item, or None when it is absent."""

    def query_pk(self, pk: str, sk_prefix: str = "") -> list[dict[str, Any]]:
        """Return items for one partition, optionally filtered by sort-key prefix."""
