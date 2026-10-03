# Three-minute demo

Speak this against the local app: `streamlit run transferlens/app.py`. The stage path uses the illustrative check layout. A second machine can use `TRANSFERLENS_RUNTIME=replay` for saved Textract and Bedrock output. Replay is labeled saved output, it is excluded from the timing numbers, and it cannot be exported as a live result.

The example figures 12 minutes, 4 minutes, 67 percent, and 3 of 3 are the metrics layout. Say them only as the layout. This script does not produce those measurements.

## 0:00 Case

Open the app. Say that TransferLens is a preflight review for a full cash transfer from fictional NorthStar Trust into an already-open LPL Traditional IRA, and that nothing is submitted to LPL. The rules are the demo policy, and they are not verified LPL processing rules.

Open demo packet TR-2026-001. Show the four documents: statement, receiving account record, client authorization, and NorthStar transfer form. The reference date is 1 September 2026.

## 0:40 Review

Move to Review and show page one of the statement. The six checks are waiting. Start the clock only if you are recording a real assisted session before the talk. For the stage demo, leave the clock alone and use the illustrative layout.

Show the illustrative checks. Source and receiving account numbers agree. The statement name John A. Smith against John Andrew Smith on the other documents needs confirmation. The statement date is 15 September 2026, after the reference date, so the future-statement check fails. Signature marks are detected on the authorization and the transfer form. Say that a model confidence score is ignored, and that each value has to be supported by text on that document.

## 1:40 Outcome

Move to Outcome. Export stays blocked while the future statement and the name confirmation are unresolved. An override requires a recorded reason. Uploading a corrected PDF starts a new run, and earlier approvals do not carry forward. This packet is the supplied clean file. It is internally consistent, and it is still blocked on the reference date because the statement is later than 1 September 2026.

## 2:20 Metrics

Move to Metrics. The tiles read Not measured until a manual baseline CSV and a completed assisted session exist. Point at the caption: 12 minutes, 4 minutes, 67 percent, and 3 of 3 describe the layout. AI processing time and replay stay out of assisted time.

## 2:45 Close

Say that local mode is the walkthrough, replay is saved extraction, and live Textract, Bedrock, S3, and the private instance wait for an approved deploy to account `884025082158` in `us-east-1`. Access to that instance is Systems Manager, with no inbound ports.
