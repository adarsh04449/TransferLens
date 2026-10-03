# TransferLens

Preflight review for a fictional full cash transfer from NorthStar Trust into an already-open LPL Traditional IRA.

This repository currently contains the first slice: configuration, the versioned demo policy, and local plus AWS storage. Document review, the Streamlit interface, and AWS deployment are not in this slice.

Local mode stores JSON metadata and uploaded bytes under `.local-data/`. Set `TRANSFERLENS_RUNTIME=replay` to use a separate saved-output directory. Set `TRANSFERLENS_RUNTIME=aws` only with a bucket name and a table name. The application uses the AWS credential chain, which on EC2 is the instance role. Do not place access keys in this repository.
