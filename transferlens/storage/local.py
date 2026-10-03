"""Directory-backed stores for local and replay runs."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from transferlens.storage.keys import EvidenceOverwriteError, StorageError
from transferlens.storage.protocol import StoredItem, StoredObject


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()

    def put_new(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._path_for(key)
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            if path.exists():
                existing = path.read_bytes()
                if hashlib.sha256(existing).hexdigest() != digest:
                    raise EvidenceOverwriteError(key)
                return StoredObject(key, digest, len(existing), content_type, created=False)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".partial")
            temporary.write_bytes(data)
            os.replace(temporary, path)
        return StoredObject(key, digest, len(data), content_type, created=True)

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise StorageError(f"Object was not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def _path_for(self, key: str) -> Path:
        if not key or key.startswith("/") or "\\" in key:
            raise StorageError("Object key must be a relative path.")
        parts = key.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise StorageError("Object key contains an empty or parent segment.")
        path = self._root.joinpath(*parts)
        return path


class LocalMetadataStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()

    def put_new(self, item: Mapping[str, Any]) -> StoredItem:
        record = _copy_item(item)
        pk, sk = record["pk"], record["sk"]
        with self._lock:
            items = self._read_partition(pk)
            if sk in items:
                return StoredItem(items[sk], created=False)
            items[sk] = record
            self._write_partition(pk, items)
        return StoredItem(record, created=True)

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read_partition(pk).get(sk)

    def query_pk(self, pk: str, sk_prefix: str = "") -> list[dict[str, Any]]:
        with self._lock:
            items = self._read_partition(pk)
        return [item for sk, item in sorted(items.items()) if sk.startswith(sk_prefix)]

    def _partition_path(self, pk: str) -> Path:
        return self._root / f"{quote(pk, safe='')}.json"

    def _read_partition(self, pk: str) -> dict[str, dict[str, Any]]:
        path = self._partition_path(pk)
        if not path.is_file():
            return {}
        document = json.loads(path.read_text(encoding="utf-8"))
        items = document.get("items", {})
        if not isinstance(items, dict):
            raise StorageError(f"Metadata partition is unreadable: {pk}")
        return items

    def _write_partition(self, pk: str, items: dict[str, dict[str, Any]]) -> None:
        path = self._partition_path(pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".partial")
        temporary.write_text(
            json.dumps({"pk": pk, "items": items}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)


def _copy_item(item: Mapping[str, Any]) -> dict[str, Any]:
    if "pk" not in item or "sk" not in item:
        raise StorageError("A metadata item needs pk and sk.")
    try:
        encoded = json.dumps(dict(item))
    except TypeError as exc:
        raise StorageError("A metadata item must be JSON data.") from exc
    return json.loads(encoded)
