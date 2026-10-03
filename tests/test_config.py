from datetime import date
from pathlib import Path

import pytest

from transferlens.config import ConfigurationError, load_settings

ROOT = Path(__file__).resolve().parents[1]


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "TRANSFERLENS_PROJECT_ROOT": str(ROOT),
        "TRANSFERLENS_DATA_DIR": ".local-data",
    }
    base.update(overrides)
    return base


def test_local_settings_use_demo_defaults() -> None:
    settings = load_settings(_env())
    assert settings.runtime == "local"
    assert settings.region == "us-east-1"
    assert settings.bedrock_model_id == "us.amazon.nova-pro-v1:0"
    assert settings.aws_profile == ""
    assert settings.demo_reference_date == date(2026, 9, 1)
    assert settings.expected_account_id == "884025082158"
    assert settings.replay is False


def test_replay_uses_a_separate_directory() -> None:
    settings = load_settings(_env(TRANSFERLENS_RUNTIME="replay"))
    assert settings.replay is True
    assert settings.data_dir.name == "replay"


def test_aws_runtime_requires_bucket_and_table() -> None:
    with pytest.raises(ConfigurationError, match="TRANSFERLENS_BUCKET"):
        load_settings(_env(TRANSFERLENS_RUNTIME="aws"))


def test_unknown_runtime_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="TRANSFERLENS_RUNTIME"):
        load_settings(_env(TRANSFERLENS_RUNTIME="silent-fallback"))
