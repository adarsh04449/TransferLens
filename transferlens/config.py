"""Runtime configuration. Credentials come from the AWS chain, never from this module."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class ConfigurationError(ValueError):
    """The process environment does not describe a usable runtime."""


@dataclass(frozen=True)
class Settings:
    runtime: str
    region: str
    aws_profile: str
    bedrock_model_id: str
    bucket: str
    table_name: str
    log_group: str
    data_dir: Path
    policy_path: Path
    expected_account_id: str
    demo_reference_date: date

    @property
    def replay(self) -> bool:
        return self.runtime == "replay"

    def require_aws(self) -> None:
        missing = [
            name
            for name, value in (
                ("TRANSFERLENS_BUCKET", self.bucket),
                ("TRANSFERLENS_TABLE", self.table_name),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "AWS runtime needs " + ", ".join(missing) + "."
            )


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    runtime = env.get("TRANSFERLENS_RUNTIME", "local").strip().lower()
    if runtime not in {"local", "replay", "aws"}:
        raise ConfigurationError(
            "TRANSFERLENS_RUNTIME must be local, replay, or aws."
        )
    root = Path(env.get("TRANSFERLENS_PROJECT_ROOT", Path.cwd()))
    data_root = Path(env.get("TRANSFERLENS_DATA_DIR", root / ".local-data"))
    if not data_root.is_absolute():
        data_root = root / data_root
    data_dir = data_root / "replay" if runtime == "replay" else data_root
    policy_path = Path(
        env.get("TRANSFERLENS_POLICY_PATH", root / "policy" / "northstar_demo_policy.json")
    )
    if not policy_path.is_absolute():
        policy_path = root / policy_path
    settings = Settings(
        runtime=runtime,
        region=env.get("AWS_REGION", env.get("AWS_DEFAULT_REGION", "us-east-1")),
        aws_profile=env.get("AWS_PROFILE", "").strip(),
        bedrock_model_id=env.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"),
        bucket=env.get("TRANSFERLENS_BUCKET", "").strip(),
        table_name=env.get("TRANSFERLENS_TABLE", "").strip(),
        log_group=env.get("TRANSFERLENS_LOG_GROUP", "").strip(),
        data_dir=data_dir,
        policy_path=policy_path,
        expected_account_id=env.get("TRANSFERLENS_EXPECTED_ACCOUNT_ID", "884025082158"),
        demo_reference_date=date.fromisoformat(
            env.get("TRANSFERLENS_DEMO_REFERENCE_DATE", "2026-09-01")
        ),
    )
    if runtime == "aws":
        settings.require_aws()
    return settings
