# AWS setup

This guide prepares a deploy. Running it creates billable resources. Do that only after the stack, region, cost, and commands below are approved, and only with a fresh workshop session.

The workshop account is `884025082158`. The region is `us-east-1`. The model is `us.amazon.nova-pro-v1:0`. The personal `default` profile is a permanent key in a different account. Do not bootstrap, synthesize, diff, deploy, or smoke-test with it.

## Workshop profile

The workshop role is the temporary federated user `WSParticipantRole/Participant`. Account ID and role name do not authenticate the CLI. Copy a fresh portal export. It has to include all three of these values together:

- `AWS_ACCESS_KEY_ID`, beginning with `ASIA`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`

Put them only in a local profile named `hackathon`, outside this repository. Do not commit them, and do not copy them into `.env`, the image, CDK code, or user data.

```bash
aws configure set profile.hackathon.region us-east-1
aws configure set profile.hackathon.aws_access_key_id ASIA...
aws configure set profile.hackathon.aws_secret_access_key ...
aws configure set profile.hackathon.aws_session_token ...
aws sts get-caller-identity --profile hackathon
```

Stop unless `Account` is `884025082158` and the ARN contains `WSParticipantRole`. `infra/guard.py` also stops synthesis when `CDK_DEFAULT_ACCOUNT` is empty, is a different account, or the region is not `us-east-1`.

The session expires. Bootstrap and deploy have to be repeated with a new export when the token dies. CloudShell in the workshop console is the fallback when the portal has no CLI credential control.

## Region and model

Confirm the session region before any stack command:

```bash
aws configure get region --profile hackathon
```

The expected value is `us-east-1`. That region is a source and destination for the US Nova Pro geo profile `us.amazon.nova-pro-v1:0`. The in-region model id is `amazon.nova-pro-v1:0`.

## Bedrock permission gaps

The instance role allows `bedrock:InvokeModel` on the inference profile and on the Nova Pro foundation model in `us-east-1`, `us-east-2`, and `us-west-2`. The participant role itself may still be unable to create IAM roles or invoke the model. After `hackathon` is confirmed, list the model:

```bash
aws bedrock list-foundation-models --profile hackathon --region us-east-1 \
  --query "modelSummaries[?modelId=='amazon.nova-pro-v1:0'].modelId"
```

`cdk deploy` is the role-creation check. If the participant role cannot create IAM roles, deploy stops with access denied. A denial describes the workshop role only.

## Tool install

The application image and the CDK app need local tools that are not part of the runtime package:

```bash
python3 --version
docker --version
python3 -m pip install -r infra/requirements.txt
npm install -g aws-cdk
```

Python 3.12 or newer is the application target. Docker builds `transferlens:local` from the repository `Dockerfile`. The CDK CLI and `aws-cdk-lib` are used only to synthesize and deploy.

## Bootstrap, synth, diff, deploy

Bootstrap once per workshop account and region. It creates the CDK toolkit bucket and roles.

```bash
export AWS_PROFILE=hackathon
export AWS_REGION=us-east-1
export CDK_DEFAULT_ACCOUNT=884025082158
export CDK_DEFAULT_REGION=us-east-1
npx cdk bootstrap aws://884025082158/us-east-1 --profile hackathon
npx cdk synth --profile hackathon
npx cdk diff --profile hackathon
npx cdk deploy TransferLensStack --profile hackathon
```

`cdk deploy` prints the bucket name, table name, log group, and instance id. Approve the IAM changes in that prompt only when they match the instance role in `docs/ARCHITECTURE.md`.

## What the stack costs while it exists

| Driver | When it bills |
| --- | --- |
| EC2 `t3.small` | While the instance is running |
| Encrypted gp3 root volume, 30 GiB | While the volume exists |
| S3 storage and requests | When documents and run artifacts are stored |
| DynamoDB on-demand | When metadata is written or read |
| CloudWatch logs, 14-day retention | When the container writes logs |
| Textract async analysis | Per page during a live extraction |
| Bedrock Nova Pro | Per token during a live extraction |
| Data transfer | While the instance reaches AWS APIs |

There is no NAT gateway, no interface VPC endpoint, no load balancer, and no public HTTP listener. Stopping the instance ends the EC2 compute charge. The volume, bucket, and table remain.

## Container start

Build the image on the reviewer machine. The image contains the app, the demo policy, the demo PDFs, and the replay fixture. It does not contain the answer key or AWS credentials.

```bash
docker build -t transferlens:local .
docker save transferlens:local | gzip > /tmp/transferlens-local.tar.gz
```

Upload the archive to the case bucket, then load it from the instance. Replace `BUCKET` and `INSTANCE_ID` with the stack outputs.

```bash
aws s3 cp /tmp/transferlens-local.tar.gz \
  s3://BUCKET/bootstrap/transferlens-local.tar.gz \
  --profile hackathon --region us-east-1
aws ssm start-session --profile hackathon --region us-east-1 --target INSTANCE_ID
```

From that shell:

```bash
aws s3 cp s3://BUCKET/bootstrap/transferlens-local.tar.gz - | gunzip | docker load
/opt/transferlens/start.sh
docker ps
```

`/opt/transferlens/env` already names the bucket, table, and log group. `AWS_PROFILE` is empty so the container uses the instance role. The process listens on `127.0.0.1:8501` inside the instance.

Forward that port to the laptop:

```bash
aws ssm start-session --profile hackathon --region us-east-1 --target INSTANCE_ID \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8501"],"localPortNumber":["8501"]}'
```

Open `http://127.0.0.1:8501`. The security group still has no inbound rules.

## Smoke test

The smoke test is the first live Textract and Bedrock run. It stays unverified until this sequence is approved and the screen is wired to the bucket.

1. Confirm the caller again with `aws sts get-caller-identity --profile hackathon`.
2. Open the forwarded app and confirm the runtime is `aws`.
3. Open demo packet TR-2026-001.
4. Extract fields. A failed Textract or Bedrock call stays failed.
5. Confirm the six checks use the returned evidence, then stop the instance if the demo is finished.

The current screen still refuses live extraction until that wiring is turned on. Replay remains the local stand-in and is excluded from assisted time.

## Expired federation

A session error, `ExpiredToken`, or an account other than `884025082158` means the export is no longer usable. Copy a new portal export into the `hackathon` profile and rerun `aws sts get-caller-identity` before the next CDK or smoke-test command.

## Common errors

| Error | What to do |
| --- | --- |
| Caller account is not `884025082158` | The shell is on the wrong profile. Switch to `hackathon` and stop. |
| `CDK_DEFAULT_ACCOUNT is empty` | Export the two CDK variables from the confirmed identity, then synthesize again. |
| `ExpiredToken` | Replace the workshop export. |
| Access denied on `iam:CreateRole` or Bedrock | The participant role cannot complete deploy or model invocation. Record the denial and stop. |
| SSM target is not connected | The instance is still booting, or it has no outbound path to Systems Manager. Check instance status and the security group outbound rule. |
| `Image transferlens:local is not loaded` | User data finished without the image. Load the archive, then run `/opt/transferlens/start.sh`. |
| Port 8501 is closed from the public internet | That is the security group. Use the port-forwarding command. |

## Safe stop and cleanup

Stop the instance to end compute charges and keep the data:

```bash
aws ec2 stop-instances --profile hackathon --region us-east-1 --instance-ids INSTANCE_ID
```

Destroy the stack only when the workshop is finished:

```bash
npx cdk destroy TransferLensStack --profile hackathon
```

Destroy removes the instance, VPC, and log group. The bucket and table are retained, including their documents and metadata. Empty and delete those two resources in the workshop console only when the case files are no longer needed. Do this with the `hackathon` profile.
