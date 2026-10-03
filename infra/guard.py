"""Refuse synthesis and deploy unless the caller is the workshop account in us-east-1."""

from __future__ import annotations

EXPECTED_ACCOUNT_ID = "884025082158"
EXPECTED_REGION = "us-east-1"


class TargetRejected(SystemExit):
    """The CDK environment is missing or is not the workshop target."""


def refuse_wrong_target(account: str, region: str) -> None:
    if not account:
        raise TargetRejected(
            "CDK_DEFAULT_ACCOUNT is empty. Select the hackathon profile before synthesizing. "
            "The personal default profile is not used."
        )
    if account != EXPECTED_ACCOUNT_ID:
        raise TargetRejected(
            f"Refusing account {account}. TransferLens deploys only to workshop account {EXPECTED_ACCOUNT_ID}."
        )
    if region != EXPECTED_REGION:
        raise TargetRejected(
            f"Refusing region {region or '(empty)'}. TransferLens deploys only in {EXPECTED_REGION}."
        )
