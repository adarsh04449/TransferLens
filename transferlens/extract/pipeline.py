"""Choose local, replay, or live extraction. A failed call stays failed."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from transferlens.config import Settings
from transferlens.evidence import FieldClaim, TextBlock
from transferlens.extract.bedrock import extract_fields
from transferlens.extract.textract import ExtractionError, line_blocks, signature_state, start_analysis, wait_for_analysis
from transferlens.signatures import SignatureObservation

_TOKEN = re.compile(r"[^A-Za-z0-9_-]")


class ExtractionUnavailable(ExtractionError):
    """This runtime cannot call Textract or Bedrock."""


@dataclass(frozen=True)
class ExtractedPacket:
    claims: tuple[FieldClaim, ...]
    blocks: tuple[TextBlock, ...]
    signatures: tuple[SignatureObservation, ...]
    replay: bool


def run_extraction(settings: Settings, case_id: str, documents: dict) -> ExtractedPacket:
    if not documents:
        raise ExtractionUnavailable("Open a packet before extracting fields.")
    if settings.runtime == "local":
        raise ExtractionUnavailable(
            "Textract and Bedrock are not called in local mode. Use replay for saved output, or aws with the workshop profile."
        )
    if settings.replay:
        return _load_replay(settings, case_id)
    if settings.aws_profile in {"", "default"}:
        raise ExtractionUnavailable(
            "Set AWS_PROFILE to the workshop profile. The personal default profile is not used."
        )
    raise ExtractionUnavailable(
        "Live extraction needs the S3 bucket from the approved deploy. It is not started from this screen yet."
    )


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


def live_document(
    textract,
    bedrock,
    model_id: str,
    role: str,
    document_id: str,
    bucket: str,
    key: str,
    sleep=None,
) -> tuple[tuple[TextBlock, ...], tuple[FieldClaim, ...], str]:
    """Run one document through Textract and one Bedrock call. Tests pass fake clients."""

    token = _TOKEN.sub("-", f"{document_id}-{key}")[:64]
    job_id = start_analysis(textract, bucket, key, token)
    raw_blocks, partial = wait_for_analysis(textract, job_id, sleep=sleep)
    blocks = line_blocks(raw_blocks, document_id)
    claims = extract_fields(bedrock, model_id, role, document_id, blocks)
    return blocks, claims, signature_state(raw_blocks, partial)
