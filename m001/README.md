# SEN Factory M001-B001

First deterministic vertical for `AI SALES LEAD QUALIFIER — M001`.

## Proven boundary

```text
local form
→ normalize
→ extract
→ qualify / score / explain
→ response draft
→ AWAITING_HUMAN_APPROVAL
→ exact SHA-256 approval
→ built-in CRM inbox
→ lead_decision_bundle_v1
→ independent durable verification
```

Before exact-hash approval the run has zero CRM rows and zero artifacts. A
stale or incorrect hash is denied. Exact approval is idempotent, so repeating
it cannot create a duplicate CRM record.

## Run locally

Python 3.12 is the only dependency.

```powershell
$env:PYTHONPATH = "src"
python -m sen_m001
```

The app binds only to `127.0.0.1`, opens the task-first form in the browser,
and stores durable state under `%LOCALAPPDATA%\SENFactoryM001` on Windows.

For an explicit data directory:

```powershell
$env:PYTHONPATH = "src"
python -m sen_m001 --data-dir .\data
```

## Evidence command

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Treat B001 as `PROVEN` only when the full suite and especially
`M001B001Proof.test_all_nine_frozen_proof_gates` pass on the current code.

The consolidated proof checks:

1. fixed lead stops at `AWAITING_HUMAN_APPROVAL`;
2. CRM and artifact counts are zero before approval;
3. a stale hash is denied without side effects;
4. exact approval creates one CRM row;
5. repeated approval creates no duplicate;
6. `lead_decision_bundle_v1` exists and matches its CAS hash;
7. close/reopen preserves exact IDs and hashes;
8. a new verifier independently validates the chain;
9. changing one artifact byte makes verification fail.

## Deferred from B001

Real LLM calls, external CRM, booking, SQLite jobs/leases, bounded retries,
installer/EXE packaging, multi-agent behavior, generic workflow machinery,
SaaS, and generic Factory UI remain outside this proof slice.
