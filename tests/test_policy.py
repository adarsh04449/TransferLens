from pathlib import Path

import pytest

from transferlens.policy import PolicyError, load_policy

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "policy" / "northstar_demo_policy.json"


def test_demo_policy_has_six_rule_groups() -> None:
    policy = load_policy(POLICY)
    assert policy["policy_id"] == "northstar-traditional-ira-demo"
    assert policy["version"] == "2026.09.01"
    assert policy["statement_max_age_days"] == 90
    assert policy["demo_reference_date"] == "2026-09-01"
    assert [group["id"] for group in policy["rule_groups"]] == [
        "documents.required_roles",
        "accounts.source_agreement",
        "accounts.receiving_agreement",
        "registration.owner_agreement",
        "statement.age_window",
        "authorization.completeness",
    ]
    assert policy["account_number_comparison"]["never_infer_digits"] is True


def test_missing_policy_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "missing.json")
