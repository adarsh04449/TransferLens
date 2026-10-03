# TransferLens

Preflight review for a fictional full cash transfer from NorthStar Trust into an already-open LPL Traditional IRA.

Supplied demo PDFs for case TR-2026-001 are in `fixtures/demo/clean/`. The answer key in `fixtures/answer_keys/` is for tests and scoring only. Code that loads the source PDFs does not read it. `benchmark/manual_baseline_template.csv` is an empty stopwatch sheet, not a measured result. The defective packet is not included.

The review engine checks cited text, then runs the six policy rules. Export stays blocked while a blocking finding is unresolved, processing has failed, or a critical value is unverified. An override requires a recorded reason. Metrics compare the manual CSV with assisted review time. Replay sessions and AI processing time stay out of that comparison. An empty baseline is not measured.

The Streamlit interface and AWS deployment are not in this slice.

Local mode stores JSON metadata and uploaded bytes under `.local-data/`. Set `TRANSFERLENS_RUNTIME=replay` to use a separate saved-output directory. Set `TRANSFERLENS_RUNTIME=aws` only with a bucket name and a table name. The application uses the AWS credential chain, which on EC2 is the instance role. Do not place access keys in this repository.
