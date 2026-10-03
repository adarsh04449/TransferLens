"""Choose local, replay, or live extraction. A failed call stays failed."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transferlens.config import Settings
from transferlens.evidence import FieldClaim, TextBlock
from transferlens.extract.bedrock import extract_fields
from transferlens.extract.textract import ExtractionError, line_blocks, signature_state, start_analysis, wait_for_analysis
from transferlens.signatures import SignatureObservation
from transferlens.storage.aws import DynamoMetadataStore, S3ObjectStore, verify_expected_account
from transferlens.storage.keys import StorageError, case_pk, document_object_key, run_artifact_key, run_sk
from transferlens.storage.protocol import MetadataStore, ObjectStore

_TOKEN = re.compile(r"[^A-Za-z0-9_-]")


class ExtractionUnavailable(ExtractionError):
    """This runtime cannot call Textract or Bedrock."""


@dataclass(frozen=True)
class ExtractedPacket:
    claims: tuple[FieldClaim, ...]
    blocks: tuple[TextBlock, ...]
    signatures: tuple[SignatureObservation, ...]
    replay: bool


@dataclass(frozen=True)
class LiveClients:
    sts: Any
    objects: ObjectStore
    textract: Any
    bedrock: Any
    metadata: MetadataStore


def run_extraction(
    settings: Settings,
    case_id: str,
    documents: dict,
    run_id: str = "run-1",
    clients: LiveClients | None = None,
) -> ExtractedPacket:
    if not documents:
        raise ExtractionUnavailable("Open a packet before extracting fields.")
    if settings.runtime == "local":
        raise ExtractionUnavailable(
            "Textract and Bedrock are not called in local mode. Use replay for saved output, or aws with the workshop profile."
        )
    if settings.replay:
        return _load_replay(settings, case_id)
    if settings.aws_profile == "default":
        raise ExtractionUnavailable(
            "The personal default profile is not used. Set AWS_PROFILE to the workshop profile, or leave it empty on the instance."
        )
    settings.require_aws()
    live = clients if clients is not None else open_live_clients(settings)
    return _extract_live(settings, case_id, documents, run_id, live)


def _load_replay(settings: Settings, case_id: str) -> ExtractedPacket:
    path = _project_root(settings) / "fixtures" / "replay" / f"{case_id}.json"
    if not path.is_file():
        raise ExtractionError(f"No saved extraction for {case_id}.")
    document = json.loads(path.read_text(encoding="utf-8"))
    claims: list[FieldClaim] = []
    blocks: list[TextBlock] = []
    signatures: list[SignatureObservation] = []
    for item in document["documents"]:
        role = item["role"]
        for block in item["blocks"]:
            blocks.append(TextBlock(block["block_id"], role, int(block["page"]), block["text"]))
        for claim in item["claims"]:
            claims.append(
                FieldClaim(
                    claim["field"],
                    role,
                    claim.get("value"),
                    role,
                    int(claim["page"]),
                    tuple(claim["source_block_ids"]),
                )
            )
        for signature in item.get("signatures") or []:
            signatures.append(
                SignatureObservation(role, role, int(signature["page"]), signature["state"], signature.get("block_id"))
            )
    return ExtractedPacket(tuple(claims), tuple(blocks), tuple(signatures), replay=True)


def _project_root(settings: Settings) -> Path:
    policy_parent = settings.policy_path.parent
    if policy_parent.name == "policy":
        return policy_parent.parent
    return policy_parent


def open_live_clients(settings: Settings) -> LiveClients:
    """Build AWS clients from the credential chain. Callers pass fakes in tests."""

    from transferlens.storage import aws_session

    session = aws_session(settings)
    return LiveClients(
        sts=session.client("sts"),
        objects=S3ObjectStore(settings.bucket, session.client("s3")),
        textract=session.client("textract"),
        bedrock=session.client("bedrock-runtime"),
        metadata=DynamoMetadataStore(session.resource("dynamodb").Table(settings.table_name)),
    )


def _extract_live(
    settings: Settings,
    case_id: str,
    documents: dict,
    run_id: str,
    clients: LiveClients,
) -> ExtractedPacket:
    try:
        verify_expected_account(clients.sts, settings.expected_account_id)
    except StorageError as exc:
        raise ExtractionUnavailable(str(exc)) from exc
    artifact_key = run_artifact_key(case_id, run_id, "extraction.json")
    if clients.objects.exists(artifact_key):
        return _packet_from_artifact(clients.objects.get(artifact_key))

    saved: list[dict] = []
    claims: list[FieldClaim] = []
    blocks: list[TextBlock] = []
    signatures: list[SignatureObservation] = []
    for role, document in documents.items():
        data = document.get("data") if isinstance(document, dict) else None
        digest = document.get("sha256") if isinstance(document, dict) else None
        if not isinstance(data, (bytes, bytearray)) or not digest:
            raise ExtractionError(f"{role} has no stored PDF bytes.")
        object_key = document_object_key(case_id, role, str(digest))
        clients.objects.put_new(object_key, bytes(data), "application/pdf")
        text_blocks, field_claims, observation, raw_blocks = live_document(
            clients.textract,
            clients.bedrock,
            settings.bedrock_model_id,
            role,
            role,
            settings.bucket,
            object_key,
        )
        claims.extend(field_claims)
        blocks.extend(text_blocks)
        signatures.append(observation)
        saved.append(
            {
                "role": role,
                "object_key": object_key,
                "blocks": [
                    {"block_id": block.block_id, "document_id": block.document_id, "page": block.page, "text": block.text}
                    for block in text_blocks
                ],
                "claims": [
                    {
                        "field": claim.field,
                        "role": claim.role,
                        "value": claim.value,
                        "document_id": claim.document_id,
                        "page": claim.page,
                        "source_block_ids": list(claim.source_block_ids),
                    }
                    for claim in field_claims
                ],
                "signature": {
                    "role": observation.role,
                    "document_id": observation.document_id,
                    "page": observation.page,
                    "state": observation.state,
                    "block_id": observation.block_id,
                },
                "raw_blocks": list(raw_blocks),
            }
        )
    clients.objects.put_new(artifact_key, json.dumps({"documents": saved}).encode("utf-8"), "application/json")
    clients.metadata.put_new(
        {
            "pk": case_pk(case_id),
            "sk": run_sk(run_id),
            "status": "extracted",
            "artifact_key": artifact_key,
        }
    )
    return ExtractedPacket(tuple(claims), tuple(blocks), tuple(signatures), replay=False)


def _packet_from_artifact(payload: bytes) -> ExtractedPacket:
    document = json.loads(payload.decode("utf-8"))
    claims: list[FieldClaim] = []
    blocks: list[TextBlock] = []
    signatures: list[SignatureObservation] = []
    for item in document["documents"]:
        for block in item["blocks"]:
            blocks.append(TextBlock(block["block_id"], block["document_id"], int(block["page"]), block["text"]))
        for claim in item["claims"]:
            claims.append(
                FieldClaim(
                    claim["field"],
                    claim["role"],
                    claim.get("value"),
                    claim["document_id"],
                    int(claim["page"]),
                    tuple(claim["source_block_ids"]),
                )
            )
        signature = item["signature"]
        signatures.append(
            SignatureObservation(
                signature["role"],
                signature["document_id"],
                int(signature["page"]),
                signature["state"],
                signature.get("block_id"),
            )
        )
    return ExtractedPacket(tuple(claims), tuple(blocks), tuple(signatures), replay=False)


def live_document(
    textract,
    bedrock,
    model_id: str,
    role: str,
    document_id: str,
    bucket: str,
    key: str,
    sleep=None,
) -> tuple[tuple[TextBlock, ...], tuple[FieldClaim, ...], SignatureObservation, tuple[dict, ...]]:
    """Run one document through Textract and one Bedrock call. Tests pass fake clients."""

    token = _TOKEN.sub("-", f"{document_id}-{key}")[:64]
    job_id = start_analysis(textract, bucket, key, token)
    raw_blocks, partial = wait_for_analysis(
        textract,
        job_id,
        sleep=time.sleep if sleep is None else sleep,
        attempts=180,
    )
    blocks = line_blocks(raw_blocks, document_id)
    claims = extract_fields(bedrock, model_id, role, document_id, blocks)
    mark = next((block for block in raw_blocks if block.get("BlockType") == "SIGNATURE" and block.get("Id")), None)
    observation = SignatureObservation(
        role,
        document_id,
        int(mark.get("Page") or 1) if mark else 1,
        signature_state(raw_blocks, partial),
        str(mark["Id"]) if mark else None,
    )
    return blocks, claims, observation, raw_blocks
