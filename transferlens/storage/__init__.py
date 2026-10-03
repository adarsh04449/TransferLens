"""Open the stores selected by runtime configuration."""

from __future__ import annotations

import os

from transferlens.config import Settings
from transferlens.storage.aws import DynamoMetadataStore, S3ObjectStore
from transferlens.storage.local import LocalMetadataStore, LocalObjectStore
from transferlens.storage.protocol import MetadataStore, ObjectStore


def aws_session(settings: Settings):
    """Open a session for the workshop profile, or the instance role when no profile is set."""

    import boto3

    if not settings.aws_profile:
        os.environ.pop("AWS_PROFILE", None)
    session_kwargs = {"region_name": settings.region}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile
    return boto3.Session(**session_kwargs)


def open_stores(settings: Settings) -> tuple[ObjectStore, MetadataStore]:
    if settings.runtime in {"local", "replay"}:
        return (
            LocalObjectStore(settings.data_dir / "objects"),
            LocalMetadataStore(settings.data_dir / "meta"),
        )
    settings.require_aws()
    session = aws_session(settings)
    s3 = session.client("s3")
    table = session.resource("dynamodb").Table(settings.table_name)
    return S3ObjectStore(settings.bucket, s3), DynamoMetadataStore(table)
