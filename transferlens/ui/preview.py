"""Labeled check layout for the screens. This is not an extraction result."""

from __future__ import annotations

from datetime import date

from transferlens.evidence import FieldClaim, TextBlock
from transferlens.review import evaluate
from transferlens.signatures import DETECTED, SignatureObservation


def illustrative_results(policy: dict, reference_date: date):
    """Run the six checks on the supplied demo packet's visible fields.

    The screen must label this as illustrative. It is not Textract or Bedrock output.
    """

    texts = {
        "statement": "Owner John A. Smith account 78451239 registration John A. Smith Traditional IRA statement date September 15, 2026",
        "receiving_account_record": "Owner John Andrew Smith LPL account 55678901 registration John Andrew Smith Traditional IRA",
        "client_authorization": "Client John Andrew Smith authorization date September 22, 2026 source account 78451239 LPL account 55678901 [X] Full transfer Liquidate all holdings and transfer cash date signed September 22, 2026",
        "northstar_transfer_form": "Name John Andrew Smith source account 78451239 receiving account 55678901 registration John Andrew Smith Traditional IRA [X] Full transfer Transfer all available cash after liquidation",
    }
    claims = (
        FieldClaim("source_account_number", "statement", "78451239", "statement", 1, ("block-1",)),
        FieldClaim("owner_name", "statement", "John A. Smith", "statement", 1, ("block-1",)),
        FieldClaim("account_registration", "statement", "John A. Smith Traditional IRA", "statement", 1, ("block-1",)),
        FieldClaim("statement_date", "statement", "September 15, 2026", "statement", 1, ("block-1",)),
        FieldClaim("owner_name", "receiving_account_record", "John Andrew Smith", "receiving_account_record", 1, ("block-1",)),
        FieldClaim("receiving_account_number", "receiving_account_record", "55678901", "receiving_account_record", 1, ("block-1",)),
        FieldClaim("account_registration", "receiving_account_record", "John Andrew Smith Traditional IRA", "receiving_account_record", 1, ("block-1",)),
        FieldClaim("owner_name", "client_authorization", "John Andrew Smith", "client_authorization", 1, ("block-1",)),
        FieldClaim("source_account_number", "client_authorization", "78451239", "client_authorization", 1, ("block-1",)),
        FieldClaim("receiving_account_number", "client_authorization", "55678901", "client_authorization", 1, ("block-1",)),
        FieldClaim("authorization_date", "client_authorization", "September 22, 2026", "client_authorization", 1, ("block-1",)),
        FieldClaim("date_signed", "client_authorization", "September 22, 2026", "client_authorization", 1, ("block-1",)),
        FieldClaim("full_transfer", "client_authorization", "true", "client_authorization", 1, ("block-1",)),
        FieldClaim("cash_transfer", "client_authorization", "true", "client_authorization", 1, ("block-1",)),
        FieldClaim("owner_name", "northstar_transfer_form", "John Andrew Smith", "northstar_transfer_form", 1, ("block-1",)),
        FieldClaim("source_account_number", "northstar_transfer_form", "78451239", "northstar_transfer_form", 1, ("block-1",)),
        FieldClaim("receiving_account_number", "northstar_transfer_form", "55678901", "northstar_transfer_form", 1, ("block-1",)),
        FieldClaim("account_registration", "northstar_transfer_form", "John Andrew Smith Traditional IRA", "northstar_transfer_form", 1, ("block-1",)),
        FieldClaim("full_transfer", "northstar_transfer_form", "true", "northstar_transfer_form", 1, ("block-1",)),
        FieldClaim("cash_transfer", "northstar_transfer_form", "true", "northstar_transfer_form", 1, ("block-1",)),
    )
    blocks = tuple(TextBlock("block-1", role, 1, text) for role, text in texts.items())
    signatures = (
        SignatureObservation("client_authorization", "client_authorization", 2, DETECTED, "sig-1"),
        SignatureObservation("northstar_transfer_form", "northstar_transfer_form", 3, DETECTED, "sig-1"),
    )
    return evaluate(
        policy,
        reference_date,
        claims,
        blocks,
        signatures,
        frozenset(policy["required_document_roles"]),
    )
