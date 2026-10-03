"""Load the versioned NorthStar demo policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    """The policy file is missing a field the review engine requires."""


REQUIRED_GROUPS = (
    "documents.required_roles",
    "accounts.source_agreement",
    "accounts.receiving_agreement",
    "registration.owner_agreement",
    "statement.age_window",
    "authorization.completeness",
)


def load_policy(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is not valid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise PolicyError("Policy file must contain a JSON object.")
    for field in ("policy_id", "version", "disclaimer", "statement_max_age_days"):
        if field not in document:
            raise PolicyError(f"Policy is missing {field}.")
    groups = document.get("rule_groups")
    if not isinstance(groups, list):
        raise PolicyError("Policy is missing rule_groups.")
    found = [group.get("id") for group in groups if isinstance(group, dict)]
    if found != list(REQUIRED_GROUPS):
        raise PolicyError(
            "Policy rule groups must be exactly "
            + ", ".join(REQUIRED_GROUPS)
            + "."
        )
    if document["statement_max_age_days"] != 90:
        raise PolicyError("This demo policy uses a 90-day statement window.")
    if "not verified LPL" not in document["disclaimer"]:
        raise PolicyError("Policy disclaimer must identify the rules as unverified.")
    return document
