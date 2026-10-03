import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra"))

from guard import EXPECTED_ACCOUNT_ID, TargetRejected, refuse_wrong_target


def test_guard_rejects_empty_and_personal_accounts():
    with pytest.raises(TargetRejected, match="empty"):
        refuse_wrong_target("", "us-east-1")
    with pytest.raises(TargetRejected, match="235494815973"):
        refuse_wrong_target("235494815973", "us-east-1")
    with pytest.raises(TargetRejected, match="us-west-1"):
        refuse_wrong_target(EXPECTED_ACCOUNT_ID, "us-west-1")
    refuse_wrong_target(EXPECTED_ACCOUNT_ID, "us-east-1")


def test_image_omits_answer_key_and_credentials():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "python:3.12" in dockerfile
    assert "fixtures/answer_keys" not in dockerfile
    assert ".env" not in dockerfile.split("ENV", 1)[1]
    assert "fixtures/answer_keys" in ignored
    assert ".env" in ignored


def test_docs_cover_the_deploy_path():
    setup = (ROOT / "docs" / "AWS_SETUP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    script = (ROOT / "docs" / "DEMO_SCRIPT.md").read_text(encoding="utf-8")
    for phrase in (
        "884025082158",
        "hackathon",
        "default",
        "cdk synth",
        "cdk diff",
        "cdk deploy",
        "ExpiredToken",
        "stop-instances",
    ):
        assert phrase in setup
    assert "no inbound" in architecture.lower() or "no inbound rules" in architecture.lower()
    assert "Not measured" in script
    assert "12 minutes" in script


def test_template_is_private_and_retained():
    pytest.importorskip("aws_cdk")
    from aws_cdk import App, Environment

    from stack import TransferLensStack

    with pytest.raises(ValueError, match="884025082158"):
        TransferLensStack(
            App(),
            "WrongAccount",
            env=Environment(account="235494815973", region="us-east-1"),
        )

    app = App()
    TransferLensStack(
        app,
        "TransferLensStack",
        env=Environment(account=EXPECTED_ACCOUNT_ID, region="us-east-1"),
    )
    assembly = app.synth()
    template = json.loads(
        Path(assembly.directory, "TransferLensStack.template.json").read_text(encoding="utf-8")
    )
    resources = template["Resources"]
    kinds = [item["Type"] for item in resources.values()]
    assert "AWS::EC2::SecurityGroupIngress" not in kinds
    assert "AWS::EC2::NatGateway" not in kinds

    buckets = [item for item in resources.values() if item["Type"] == "AWS::S3::Bucket"]
    tables = [item for item in resources.values() if item["Type"] == "AWS::DynamoDB::Table"]
    groups = [item for item in resources.values() if item["Type"] == "AWS::Logs::LogGroup"]
    instances = [item for item in resources.values() if item["Type"] == "AWS::EC2::Instance"]
    assert len(buckets) == 1
    assert len(tables) == 1
    assert len(groups) == 1
    assert len(instances) == 1

    bucket = buckets[0]
    assert bucket["DeletionPolicy"] == "Retain"
    access = bucket["Properties"]["PublicAccessBlockConfiguration"]
    assert access["BlockPublicAcls"] is True
    assert access["RestrictPublicBuckets"] is True
    assert bucket["Properties"]["BucketEncryption"]["ServerSideEncryptionConfiguration"][0][
        "ServerSideEncryptionByDefault"
    ]["SSEAlgorithm"] == "AES256"

    table = tables[0]
    assert table["DeletionPolicy"] == "Retain"
    assert table["Properties"]["BillingMode"] == "PAY_PER_REQUEST"
    index_names = [item["IndexName"] for item in table["Properties"]["GlobalSecondaryIndexes"]]
    assert index_names == ["status-index"]

    assert groups[0]["Properties"]["RetentionInDays"] == 14

    instance = instances[0]["Properties"]
    assert instance["MetadataOptions"]["HttpTokens"] == "required"
    assert instance["MetadataOptions"]["HttpPutResponseHopLimit"] == 2
    assert "SecurityGroupIngress" not in instance
    script = _user_data_text(instance["UserData"])
    assert "TRANSFERLENS_RUNTIME=aws" in script
    assert "127.0.0.1:8501" in script
    assert "ASIA" not in script
    assert "AWS_SECRET_ACCESS_KEY" not in script
    assert "AWS_SESSION_TOKEN" not in script
    assert "AWS_PROFILE=" not in script

    statements = []
    for item in resources.values():
        if item["Type"] != "AWS::IAM::Policy":
            continue
        statements.extend(item["Properties"]["PolicyDocument"]["Statement"])
    actions = {action for statement in statements for action in _as_list(statement["Action"])}
    assert "textract:StartDocumentAnalysis" in actions
    assert "textract:GetDocumentAnalysis" in actions
    assert "bedrock:InvokeModel" in actions


def _user_data_text(user_data: dict) -> str:
    payload = user_data["Fn::Base64"]
    if isinstance(payload, str):
        return payload
    parts = payload["Fn::Join"][1]
    return "".join(part for part in parts if isinstance(part, str))


def _as_list(value):
    return value if isinstance(value, list) else [value]
