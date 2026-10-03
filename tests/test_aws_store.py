from botocore.exceptions import ClientError

from transferlens.storage.aws import (
    DynamoMetadataStore,
    S3ObjectStore,
    verify_expected_account,
)
from transferlens.storage.keys import EvidenceOverwriteError, StorageError
import pytest


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def head_object(self, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "missing"}}, "HeadObject")
        return {"Bucket": Bucket}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str, Metadata: dict) -> dict:
        self.objects[Key] = Body
        return {}

    def get_object(self, Bucket: str, Key: str) -> dict:
        return {"Body": _Body(self.objects[Key])}


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def put_item(self, Item: dict, ConditionExpression: str) -> dict:
        key = (Item["pk"], Item["sk"])
        if key in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                "PutItem",
            )
        self.items[key] = dict(Item)
        return {}

    def get_item(self, Key: dict) -> dict:
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": dict(item)} if item else {}

    def query(self, **kwargs: object) -> dict:
        values = kwargs["ExpressionAttributeValues"]
        pk = values[":pk"]
        prefix = values[":prefix"]
        items = [
            dict(item)
            for (item_pk, sk), item in self.items.items()
            if item_pk == pk and sk.startswith(prefix)
        ]
        return {"Items": items}


class FakeSTS:
    def __init__(self, account: str) -> None:
        self._account = account

    def get_caller_identity(self) -> dict[str, str]:
        return {"Account": self._account, "Arn": "arn:aws:sts::example:assumed-role/WSParticipantRole/Participant"}


def test_s3_store_refuses_to_replace_evidence() -> None:
    store = S3ObjectStore("demo-bucket", FakeS3())
    assert store.put_new("cases/c/documents/d/hash.pdf", b"one", "application/pdf").created is True
    assert store.put_new("cases/c/documents/d/hash.pdf", b"one", "application/pdf").created is False
    with pytest.raises(EvidenceOverwriteError):
        store.put_new("cases/c/documents/d/hash.pdf", b"two", "application/pdf")


def test_dynamodb_put_is_idempotent() -> None:
    store = DynamoMetadataStore(FakeTable())
    item = {"pk": "CASE#case-1", "sk": "EVENT#started", "event_type": "review_started"}
    assert store.put_new(item).created is True
    again = store.put_new({**item, "event_type": "review_finished"})
    assert again.created is False
    assert again.item["event_type"] == "review_started"
    assert len(store.query_pk("CASE#case-1", "EVENT#")) == 1


def test_account_guard_accepts_only_the_hackathon_account() -> None:
    assert verify_expected_account(FakeSTS("884025082158"), "884025082158") == "884025082158"
    with pytest.raises(StorageError, match="does not match"):
        verify_expected_account(FakeSTS("235494815973"), "884025082158")
