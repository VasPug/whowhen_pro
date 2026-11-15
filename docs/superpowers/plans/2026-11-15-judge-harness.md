# Judge Harness Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave a reproducible three-condition pilot runnable with only an OpenRouter API key.

**Architecture:** An experiment package wraps the unchanged baseline renderers/parser/scorer. A shared sanitized source bundle feeds baseline, AgentRx-inspired, and RAFFLES-inspired workflows; a bounded provider client records calls, and a manifest-based runner isolates configurations and produces paired reports.

**Tech Stack:** Python 3.10+, existing PyYAML/renderers/scorer, standard-library HTTP/filesystem/CLI, pytest. No new runtime dependency is needed for orchestration.

**Spec:** `docs/superpowers/specs/2026-11-15-judge-harness-experiment-design.md`

## Global Constraints

- All model roles use `qwen/qwen3.5-122b-a10b` via OpenRouter, provider `alibaba`, fallback disabled. The public endpoints listing was checked on 2026-11-15. Hosted weights cannot be independently checksum-verified; log returned model/provider metadata.
- Default pilot: text only, 24 evaluation traces, 6 disjoint development traces, one repetition, seed 20261115, at most 12 rendered steps and 12,000 source characters. It is exploratory, not a full paper reproduction.
- Pin dataset revision `0bd196c8a040841c4ae167ab33cc8151de246f1f`; use that revision's actual taxonomy and verify gold-label coverage. Do not silently use the paper's stated mode count.
- Baseline remains byte-equivalent to upstream prompt construction. All alternatives use only baseline-visible source material; hidden labels and metadata stay in scorer storage.
- Default temperature 0, reasoning disabled consistently, 2,048 output tokens/call, 60,000 input-character limit/call, 3 constraints per step, 12,000 evidence characters, 2 review cycles, 120-second timeout, 2 transport retries, sequential scheduling, $25 reservation ceiling. No paid calls during implementation.
- Default sampling is label-independent, seeded, grouped by benchmark plus normalized task query and balanced across frameworks by round-robin selection. The manifest freezes development/evaluation membership and all exclusions.
- Primary fixed-denominator error-mode F1 and Who/When/All use upstream aggregation; unusable runs count wrong. Preserve canonical-mode versus accepted-alternative distinction.
- Record every call, retry, failure, effective request configuration, identity hash, and source hash. Secrets are environment-only and never logged.

## Review Focus

- Labels/injection markers hidden in extras, raw IDs, or task answers must not reach model calls (Task 1).
- Same config with modified data/code/prompts must not reuse cached results (Tasks 1 and 4).
- Malformed JSON, nonexistent references, and model-written arithmetic operands must not become fabricated deterministic evidence (Task 2).
- Retries, interrupted runs, missing usage, and exhausted budget must not exceed reserved bounds or hide missing denominator rows (Tasks 3 and 4).
- Empty cohorts, single-agent-only data, absent modes, paired grouping, and partial runs must yield explicit reports, not misleading comparisons (Task 4).

## Task 1: Frozen data and shared source bundle

**Files:** Create `whowhen_eval/experiment/{__init__,config,data}.py`, `configs/judge-harness.yaml`, `tests/test_experiment_data.py`.

**Interfaces:** `load_config(path) -> dict`; `prepare(config, data_root, run_root) -> Path`; `bundle(release, taxonomy) -> dict` with original `baseline_parts`, normalized `events`, `task`, `step_format_hint`, and `source_hash`. Prepared directory holds manifest, visible cases, evaluation-only labels, and taxonomy.

- [ ] Write tests for config bounds, exact baseline parity, hidden-label stripping, stable grouping/sampling, source/code/config identity, and corrupt downloads.
- [ ] Run `python -m pytest tests/test_experiment_data.py -q`; verify failure from missing implementation.
- [ ] Implement revision-pinned downloads with SHA256 checks and atomic replacement; deterministic normalization over renderer blocks; prepare fixed cohort and disjoint dev groups. Only text supported in initial runner; reject other modalities explicitly.
- [ ] Run tests and verify pass; audit real pinned data taxonomy coverage.
- [ ] Commit Task 1 and ledger results.

## Task 2: Harness workflows

**Files:** Create `whowhen_eval/experiment/{harnesses,checks}.py`, `tests/test_experiment_harnesses.py`.

**Interfaces:** `run_harness(name, case, taxonomy, config, call) -> dict`; injected `call(role, parts) -> str` records usage externally. `check_constraint(constraint, evidence_sources) -> dict` validates references and executes allowlisted comparisons. Results include parsed prediction and intermediate audit.

- [ ] Write tests for one-call baseline parity, prefix-only constraint generation, validated evidence references, numeric extraction anchored to source spans, semantic/inconclusive routing, no arbitrary execution, 10-call review cap, disagreement, malformed revision fallback, and invalid intermediate responses.
- [ ] Verify tests fail, then implement task-level requirements plus per-step constraints/checks and joint final judgment; implement four-reviewer bounded review loop with structural validation.
- [ ] Run targeted tests and Task 1 tests; verify pass.
- [ ] Commit Task 2 and ledger results.

## Task 3: Bounded provider calls

**Files:** Create `whowhen_eval/experiment/client.py`, `tests/test_experiment_client.py`.

**Interfaces:** `Client(config, audit_path, budget_path, offline=False)` callable as `client(role, parts) -> str`. Inject HTTP transport in tests. Persistent budget reserves conservative input-byte/output-token upper cost before each attempt; budget is shared across resume.

- [ ] Write tests for exact provider routing, missing-key error, key redaction, transient-only retries, persistent reservations, input overflow, missing usage, response model mismatch, and offline labeling.
- [ ] Verify failure, then implement standard-library OpenRouter requests with no implicit fallback or dropped parameters, explicit backoff and bounded cost. Offline responses exercise workflows but are never represented as model results.
- [ ] Run targeted tests; verify pass.
- [ ] Commit Task 3 and ledger results.

## Task 4: Resumable CLI and reports

**Files:** Create `whowhen_eval/experiment/{__main__,runner,report}.py`, `tests/test_experiment_runner.py`.

**Interfaces:** CLI subcommands `prepare`, `run`, `report`, `doctor`; all accept `--config`. `run` supports `--offline` and reuses atomic per-condition/per-repetition result files. `summarize(run_dir) -> dict` produces JSON, Markdown and per-mode CSV.

- [ ] Write tests for complete three-arm offline run, resume without repeat calls, run locking, manifest/input mutation rejection, fixed-denominator failed/unrun cases, no live/offline cache collisions, partial-report warning, paired clustered intervals and correct framework weighting.
- [ ] Verify failure, then implement deterministic interleaving, shared budget, atomic results, lightweight file lock, complete accounting and reports. Bootstrap 1,000 paired samples for exploratory 95% intervals; report two comparisons without confirmatory significance claims.
- [ ] Run all experiment tests and upstream tests; verify pass.
- [ ] Commit Task 4 and ledger results.

## Task 5: Ready-to-run delivery

**Files:** Create `scripts/run-judge-experiment.sh`, `docs/judge-harness-quickstart.md`, `.env.example`; update `README.md`, `pyproject.toml`, spec implementation addendum and this plan.

- [ ] Add a launcher test showing an unset key fails clearly before any paid request and the offline mode runs without a key.
- [ ] Implement launcher: create/use local venv, install package, prepare pinned data, run all three conditions, produce report; prompt silently for key only in an interactive terminal if unset, never write it to disk. CLI entry point `whowhen-experiment`.
- [ ] Install in the worktree venv; prepare real data; run `doctor`, full offline workflow, and upstream real-data scorer checks. Verify no paid request was made.
- [ ] Obtain independent whole-branch review, fix material findings with regression tests, rerun suite, freeze exact dependencies for reproduction, commit completed work.
- [ ] Deliver launcher command, API-key provider, report locations, defaults and verification limitations. Keep feature branch/worktree available; no push or merge requested.

## Execution decisions

The user explicitly requested planning followed by unattended implementation, so no additional plan-approval pause is needed. The unresolved spec settings above are now conservative, editable defaults. These choices limit the initial claim to a text-only pilot; broader modality coverage and equal-compute comparisons remain outside this implementation.
