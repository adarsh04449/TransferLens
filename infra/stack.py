"""Private TransferLens workspace. No inbound ports and no public application URL."""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from guard import EXPECTED_ACCOUNT_ID, EXPECTED_REGION

MODEL_ID = "us.amazon.nova-pro-v1:0"
FOUNDATION_MODEL = "amazon.nova-pro-v1:0"
BEDROCK_REGIONS = ("us-east-1", "us-east-2", "us-west-2")


class TransferLensStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if self.account != EXPECTED_ACCOUNT_ID or self.region != EXPECTED_REGION:
            raise ValueError(
                f"TransferLensStack accepts only account {EXPECTED_ACCOUNT_ID} in {EXPECTED_REGION}."
            )

        bucket = s3.Bucket(
            self,
            "Documents",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )
        table = dynamodb.Table(
            self,
            "Metadata",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        log_group = logs.LogGroup(
            self,
            "WorkspaceLogs",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        vpc = ec2.Vpc(
            self,
            "Vpc",
            availability_zones=["us-east-1a"],
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24)
            ],
        )
        security_group = ec2.SecurityGroup(
            self,
            "WorkspaceSecurityGroup",
            vpc=vpc,
            description="No inbound rules. Reach the workspace through Systems Manager.",
            allow_all_outbound=True,
        )
        role = iam.Role(
            self,
            "WorkspaceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="TransferLens instance role. Credentials stay on the instance.",
        )
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        bucket.grant_read_write(role)
        table.grant_read_write_data(role)
        log_group.grant_write(role)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["textract:StartDocumentAnalysis", "textract:GetDocumentAnalysis"],
                resources=["*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{EXPECTED_REGION}:{EXPECTED_ACCOUNT_ID}:inference-profile/{MODEL_ID}",
                    *[
                        f"arn:aws:bedrock:{region}::foundation-model/{FOUNDATION_MODEL}"
                        for region in BEDROCK_REGIONS
                    ],
                ],
            )
        )

        instance = ec2.Instance(
            self,
            "Workspace",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=security_group,
            role=role,
            require_imdsv2=True,
            associate_public_ip_address=True,
            user_data=_user_data(bucket.bucket_name, table.table_name, log_group.log_group_name),
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                )
            ],
        )
        cfn_instance = instance.node.default_child
        cfn_instance.add_property_override("MetadataOptions.HttpTokens", "required")
        cfn_instance.add_property_override("MetadataOptions.HttpPutResponseHopLimit", 2)

        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "TableName", value=table.table_name)
        CfnOutput(self, "LogGroupName", value=log_group.log_group_name)
        CfnOutput(self, "InstanceId", value=instance.instance_id)


def _user_data(bucket_name: str, table_name: str, log_group_name: str) -> ec2.UserData:
    user_data = ec2.UserData.for_linux()
    user_data.add_commands(
        "set -euxo pipefail",
        "dnf install -y docker",
        "systemctl enable --now docker",
        "mkdir -p /opt/transferlens",
        "cat > /opt/transferlens/env <<'EOF'",
        "TRANSFERLENS_RUNTIME=aws",
        "AWS_REGION=us-east-1",
        "AWS_DEFAULT_REGION=us-east-1",
        "BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0",
        f"TRANSFERLENS_BUCKET={bucket_name}",
        f"TRANSFERLENS_TABLE={table_name}",
        f"TRANSFERLENS_LOG_GROUP={log_group_name}",
        "TRANSFERLENS_EXPECTED_ACCOUNT_ID=884025082158",
        "TRANSFERLENS_DEMO_REFERENCE_DATE=2026-09-01",
        "EOF",
        "chmod 644 /opt/transferlens/env",
        "cat > /opt/transferlens/start.sh <<'EOF'",
        "#!/bin/bash",
        "set -euo pipefail",
        'if ! docker image inspect transferlens:local >/dev/null 2>&1; then',
        '  echo "Image transferlens:local is not loaded. See docs/AWS_SETUP.md."',
        "  exit 0",
        "fi",
        "docker rm -f transferlens >/dev/null 2>&1 || true",
        "docker run -d --name transferlens --restart unless-stopped \\",
        "  --env-file /opt/transferlens/env \\",
        "  --log-driver awslogs \\",
        "  --log-opt awslogs-region=us-east-1 \\",
        f"  --log-opt awslogs-group={log_group_name} \\",
        "  --log-opt awslogs-create-group=false \\",
        "  --log-opt awslogs-stream=workspace \\",
        "  -p 127.0.0.1:8501:8501 \\",
        "  transferlens:local",
        "EOF",
        "chmod 755 /opt/transferlens/start.sh",
        "/opt/transferlens/start.sh",
    )
    return user_data
