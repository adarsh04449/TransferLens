"""S3 and DynamoDB stores. Callers pass clients so tests do not contact AWS."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from botocore.exceptions import ClientError

from transferlens.storage.keys import EvidenceOverwriteError, StorageError
from transferlens.storage.protocol import StoredItem, StoredObject

_MISSING = {"404", "NoSuchKey", "NotFound"}


class S3ObjectStore:
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def put_new(self, key: str, data: bytes, content_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in _MISSING:
                raise StorageError(f"Could not inspect object {key}.") from exc
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": digest},
            )
            return StoredObject(key, digest, len(data), content_type, created=True)
        existing = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        if hashlib.sha256(existing).hexdigest() != digest:
            raise EvidenceOverwriteError(key)
        return StoredObject(key, digest, len(existing), content_type, created=False)

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _MISSING:
                raise StorageError(f"Object was not found: {key}") from exc
            raise StorageError(f"Could not read object {key}.") from exc
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _MISSING:
                return False
            raise StorageError(f"Could not inspect object {key}.") from exc
        return True


class DynamoMetadataStore:
    def __init__(self, table: Any) -> None:
        self._table = table

    def put_new(self, item: Mapping[str, Any]) -> StoredItem:
        record = dict(item)
        if "pk" not in record or "sk" not in record:
            raise StorageError("A metadata item needs pk and sk.")
        try:
            self._table.put_item(
                Item=record,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise StorageError("Could not write metadata.") from exc
            existing = self.get(str(record["pk"]), str(record["sk"]))
            if existing is None:
                raise StorageError("An existing metadata item could not be read.") from exc
            return StoredItem(existing, created=False)
        return StoredItem(record, created=True)

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        response = self._table.get_item(Key={"pk": pk, "sk": sk})
        item = response.get("Item")
        return dict(item) if item else None

    def query_pk(self, pk: str, sk_prefix: str = "") -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": pk, ":prefix": sk_prefix},
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self._table.query(**kwargs)
            items.extend(dict(item) for item in response.get("Items", []))
            token = response.get("LastEvaluatedKey")
            if not token:
                return items
            kwargs["ExclusiveStartKey"] = token


def verify_expected_account(sts_client: Any, expected_account_id: str) -> str:
    """Return the caller account when it matches. Raise before any deploy or smoke test."""

    identity = sts_client.get_caller_identity()
    account = identity["Account"]
    if account != expected_account_id:
        raise StorageError(
            f"AWS caller account {account} does not match the hackathon account."
        )
    return account
