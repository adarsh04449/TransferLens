"""CDK entry point. This file does not deploy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from aws_cdk import App, Environment

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard import refuse_wrong_target
from stack import TransferLensStack


def main() -> None:
    account = os.environ.get("CDK_DEFAULT_ACCOUNT", "").strip()
    region = os.environ.get("CDK_DEFAULT_REGION", "").strip()
    refuse_wrong_target(account, region)
    app = App()
    TransferLensStack(
        app,
        "TransferLensStack",
        env=Environment(account=account, region=region),
    )
    app.synth()


if __name__ == "__main__":
    main()
