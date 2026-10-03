"""Asynchronous Textract analysis for a multipage PDF already stored in S3."""

from __future__ import annotations

from collections.abc import Callable

from transferlens.evidence import TextBlock
from transferlens.signatures import ABSENT, DETECTED, NEEDS_CONFIRMATION


class ExtractionError(RuntimeError):
    """Textract or Bedrock failed. The failure is not replaced with a fixture."""


def start_analysis(client, bucket: str, key: str, token: str) -> str:
    response = client.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["FORMS", "SIGNATURES", "LAYOUT"],
        ClientRequestToken=token[:64],
    )
    job_id = response.get("JobId")
    if not job_id:
        raise ExtractionError("Textract did not return a job id.")
    return job_id


def wait_for_analysis(
    client,
    job_id: str,
    sleep: Callable[[float], None] | None = None,
    attempts: int = 20,
) -> tuple[tuple[dict, ...], bool]:
    blocks: list[dict] = []
    token = None
    partial = False
    pauses = 0
    while pauses + 1 <= attempts:
        kwargs: dict = {"JobId": job_id, "MaxResults": 1000}
        if token:
            kwargs["NextToken"] = token
        page = client.get_document_analysis(**kwargs)
        status = page.get("JobStatus")
        if status == "FAILED":
            message = page.get("StatusMessage") or "Textract failed."
            raise ExtractionError(message)
        if status == "IN_PROGRESS":
            pauses += 1
            if sleep is not None:
                sleep(1)
            continue
        if status not in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
            raise ExtractionError(f"Textract returned {status}.")
        blocks.extend(page.get("Blocks") or [])
        partial = partial or status == "PARTIAL_SUCCESS"
        token = page.get("NextToken")
        if not token:
            return tuple(blocks), partial
    raise ExtractionError("Textract did not finish.")


def line_blocks(blocks: tuple[dict, ...] | list[dict], document_id: str) -> tuple[TextBlock, ...]:
    lines = []
    for block in blocks:
        if block.get("BlockType") != "LINE" or not block.get("Id"):
            continue
        lines.append(
            TextBlock(
                block_id=str(block["Id"]),
                document_id=document_id,
                page=int(block.get("Page") or 1),
                text=str(block.get("Text") or ""),
            )
        )
    return tuple(lines)


def signature_state(blocks: tuple[dict, ...] | list[dict], partial: bool) -> str:
    if partial:
        return NEEDS_CONFIRMATION
    marks = [block for block in blocks if block.get("BlockType") == "SIGNATURE"]
    if not marks:
        return ABSENT
    if any(block.get("Confidence") is None for block in marks):
        return NEEDS_CONFIRMATION
    return DETECTED
