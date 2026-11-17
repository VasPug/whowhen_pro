# Run the judge-harness experiment

Run from this feature checkout on Linux/macOS with Python 3.10 or newer:

```bash
bash scripts/run-judge-experiment.sh
```

The launcher asks for your **OpenRouter API key** without displaying or saving it. If `OPENROUTER_API_KEY` is already exported, it uses that variable. Noninteractive execution requires the variable. Do not paste a key into this chat or commit it. The account needs access/credit for the configured model.

The launcher sets up a local virtual environment if needed, downloads/checks the pinned public text dataset (about 76 MB), prepares the fixed cohort, validates the key through OpenRouter's nonbillable key endpoint, runs all three conditions, and prints the report path. The provided workspace is already prepared. No paid call was made during development. Authentication and real Qwen response compatibility still require the first live run.

## Defaults

| Setting | Value |
|---|---|
| Model | Qwen3.5-122B-A10B via OpenRouter |
| Provider | Alibaba only; fallback disabled; required parameters enforced |
| Arms | Existing all-at-once, AgentRx-inspired, RAFFLES-inspired |
| Cohort | 24 short text traces; 6 separate development task groups |
| Repetitions | 1; exploratory pilot |
| Source filter | At most 12 rendered steps and 12,000 prompt characters, including taxonomy |
| Model settings | Temperature 0; reasoning disabled; max 2,048 output tokens per call |
| Review loop | At most two cycles; fault/decisiveness/primacy/taxonomy reviewers |
| Calls | Baseline 1; AgentRx at most 50 under defaults; RAFFLES at most 10; transport retries additional |
| Budget | $25 conservative reservation ceiling for the whole live run, including retries |
| Scheduling | Sequential, deterministically shuffled across conditions/cases |
| Primary metric | Error-mode macro-F1; failed/unusable runs remain in the denominator |

These are implementation defaults chosen for unattended setup, not a preregistered full-benchmark study. The short-trace filter excludes many examples and some frameworks. Check the manifest/report exclusion counts and per-mode support before interpreting results. Six development cases are prepared but never included in the evaluation command; no model-based tuning has occurred on either partition.

The pinned released taxonomy has **17 modes**; its text split uses 14 of them. This differs from the paper's advertised 18-mode vocabulary. The runner uses the release's own definitions and verifies label coverage. Results target this release, not an exact reproduction of the paper's tables.

Provider/model names are fixed across calls, with response metadata logged. Hosted model weights/quantization cannot be independently frozen or checksum-verified. Model/provider availability, account permissions, and service behavior may change.

## Validate without a key

```bash
bash scripts/run-judge-experiment.sh --offline
.venv/bin/python -m whowhen_eval.experiment doctor --config configs/judge-harness.yaml
```

Offline mode uses deterministic synthetic responses and exercises orchestration and reporting. Its scores are **not research results** and are stored separately from live results. It deliberately runs both review cycles. Unit tests separately exercise nonempty evidence, numeric checks, and semantic checks.

## Outputs and resume

Each configuration/data/code combination creates a separate directory under `experiment-runs/`. Its manifest freezes the sampled IDs, source hashes, framework membership, exclusions and all effective settings. `cases/` contains only judge-visible input; `labels.json` is evaluation-only. No model call receives the raw dataset row or label sidecar.

Within `live/` or `offline/`:

- `report.md`: metric comparison and paired changes.
- `report.json`: per-repetition metrics, confusion matrices, resource usage, completion rates and successful-record-only scores for comparison.
- `per-mode.csv`: precision, recall, F1 and support per error category/repetition.
- `results/`: final per-condition/per-case records, including failures and harness evidence/reviews.
- `calls/`: durable attempt-start records and matching completion/error records with prompts, responses and usage. These contain benchmark content, never the API key. Starts without completions are reported as unknown-outcome attempts; their reservations persist.
- `budget.json`: spending reservations, retained across restarts.

Run the same command to resume. Completed records, including recorded failures, are not automatically rerun; this prevents silently selecting better attempts or spending indefinitely. An interrupted in-progress case may be run again, with all previous reservations retained. Offline results cannot satisfy a live run. One process may hold the experiment lock at a time.

Invalid credentials, insufficient account credit, and global routing/configuration errors stop the run without caching the affected case as a failure. Correct the key/account issue and rerun the same command. Already completed cases remain intact; unscheduled cases remain visibly missing until resumed.

Exit code 0 means every scheduled result completed without harness/transport failures; 3 means recorded failures remain; 2 means the report is incomplete; 1 indicates setup/configuration trouble. A parseable but partly missing attribution is recorded with parser warnings and scored per available field, just as upstream does. Missing final fields count wrong on their respective axes; transport/budget failures still fail the trial. Review disagreement at the cap can still produce a valid final result.

## Change the experiment

Edit `configs/judge-harness.yaml` before starting. All defaults and supported keys are in `whowhen_eval/experiment/config.py`; unknown keys or unsupported modalities are rejected. Changing config, pinned data hashes, or implementation code creates a fresh identity and budget. Do not interpret a fresh run budget as an account-wide spending cap.

The $25 ceiling is deliberately conservative: every attempted request reserves an upper estimate based on UTF-8 input size, output-token limit and configured price ceilings. Reservations are not refunded, even when actual usage is lower or a request fails. Provider price caps are sent in each request. The run can stop requesting early while actual charges are below $25. Actual reported costs and missing-usage counts are shown separately. Higher prices or unavailable providers produce errors rather than silent fallback. Budget-exhausted scheduled cases are recorded as failures.

The first implementation is text-only. It does not silently discard images or support video without their assets. It does not execute generated constraints, replay agents, or perform interventions. Additional generated context/calls are part of each harness, so results do not isolate structure from extra compute.

For a larger run, increase cohort/repetitions and review the cost and length limits first. Keep model settings and source information shared. Independent repeats at temperature zero still do not guarantee distinct samples; provider determinism is not assumed.

## Reproduce and test

```bash
.venv/bin/python -m pip install -r requirements-experiment.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
.venv/bin/python -m tests.test_scorer --data-root experiment-data --framework macnet
```

`requirements-experiment.lock` records the tested environment's package versions. A different OS/Python version may need compatible wheels. Source inputs, prompts, settings and code hashes are pinned separately in the manifest.

The original full-dataset tests skip when `WHOWHEN_DATA` is unset. Setting it for the full suite requires the missing image/video splits as well; the framework-specific command above works with this text-only download. Development verification also checked representative traces from all eight text frameworks and the alternate-label scoring case.

Design: [experiment specification](superpowers/specs/2026-11-15-judge-harness-experiment-design.md). Implementation: [plan](superpowers/plans/2026-11-15-judge-harness.md).

## Deterministic parsing and degraded evidence (2026-11-16)

All final diagnoses use the unchanged upstream four-field parser. Intermediate
JSON accepts a single complete object surrounded by prose or code fences. Broken
JSON is not guessed or repaired with another model call.

Unusable requirement entries are dropped individually with audit warnings; unreadable
requirement/constraint lists contribute no checks and are explicitly warned about.
Lists over the configured limit are truncated deterministically. A malformed
constraint, semantic check, or reviewer response becomes inconclusive, with no
accepted evidence. Other usable entries and the final diagnosis continue.
Exact source citations and numeric grounding remain required to accept evidence;
a rejected quote no longer rejects the entire trial. Inconclusive reviewers cannot
trigger consensus. RAFFLES retains its latest structurally valid diagnosis, or
returns the final partial diagnosis through the upstream parser if none was valid.

Warnings are stored in `audit.parse_warnings`, and original responses remain in
call logs. A completed trial means the workflow returned a diagnosis, not that all
checks succeeded or the diagnosis was correct. Inspect warnings/inconclusive checks
alongside scores. No extra model calls or formatting retries were added.

This extends the upstream parser's tolerant failure policy to our custom intermediate
formats; it is not a claim that Who&When Pro implements these evidence stages.
The code hash changes, so prepare a new run; previous results are retained unchanged.
Prior pilot outcomes must not be relabeled as results of this corrected harness.

## Source-ID integration (2026-11-17)

This supersedes the earlier exact-quotation requirement for semantic evidence.
AgentRx and RAFFLES share a deterministic source resolver: accept an ID string or
an object containing `ref`, retrieve the original recorded text, and discard any
model-supplied quote/extra fields. Unknown or future references remain invalid;
conclusive checks/reviews require nonempty evidence. Valid IDs establish source
location, not semantic truth. Numeric operands retain exact span/value checks.

Reviewer prompts now have one review contract without the baseline diagnosis
instructions. Both harnesses request JSON output, with schemas where applicable;
parsers still handle equivalent ID representations because the provider did not
consistently enforce the requested schema. Requirements prioritize the main task
before formatting. Revision histories use compact IDs plus source coordinates;
full retrieved text remains in audits. The final four-field parser, baseline prompt,
model settings, sample selection and scoring formulas are unchanged.

The six original development cases are tested separately with
`scripts/validate-source-id-development.py`. A new evaluation identity is generated
for the integrated implementation. Prior inspected 24-case pilot results are retained;
a repeat on those cases is debugging/evaluation evidence, not a new held-out study.
