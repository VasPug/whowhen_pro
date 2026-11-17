# Evidence Validation Probes Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Track progress below.

**Goal:** Test citation recovery and output-format alternatives before another evaluation.
**Architecture:** Isolated probe module reuses existing client/data, with a standalone
citation locator. Production harness defaults remain unchanged.
**Tech Stack:** Python, pytest, existing OpenRouter client, JSON Schema.
**Spec:** docs/superpowers/specs/2026-11-16-evidence-validation-probe-design.md

## Global Constraints
Same Qwen/Alibaba/decoding. Six development cases. $5 total ceiling. No evaluation
labels in model calls. Preserve both existing runs. Report usability, not new F1.

## Review Focus
Wrong-step references must never auto-remap. Numeric/sign/negation changes must not
be normalized away. Ellipsis recovery is location only. Schema must be logged and
budgeted. Resume must not mix different probe requests/results.

### Task 1: Matching and transport
- [x] Write tests for harmless whitespace/quotes/task aliases, wrong steps, changed
  numbers/negation, ambiguous and qualified ellipses, plus schema transport logging.
- [x] Run tests RED; implement evidence.locate(ref,sources,policy) returning status,
  canonical source/span and recovery method; add optional response_format to Client.
- [x] Run targeted tests GREEN then full suite.

### Task 2: Development probes
- [x] Implement validation_probe CLI offline/live using saved response sources,
  deterministic shuffled probe variants and identical shared per-case candidates.
- [x] Verify no hidden labels in generated prompts, ID validation and separate
  shape/grounding/semantic results; run full tests.
- [x] Run offline audit and live probes; manually inspect samples. Export report,
  logs and source snapshots. Review conclusions against actual outcomes.

## Progress / rulings
- User requested autonomous tests, so no additional design approval requested.
- Existing isolated codex/judge-harness worktree reused; previous edits preserved.
- Skill helper scripts unavailable as filesystem paths; this file is the ledger.
- Pre-flight: matcher feeds probe analysis; client optional schema feeds probe calls.

- Task 1: matching/schema tests passed; full suite 69 passed, 2 skipped before review.
- Final review: four findings reproduced RED; fixing numeric endpoint tokens, output
  lock, taxonomy/source integrity, and shared requirements for semantic comparison.
- Ruling: both semantic variants use the same source-ID-derived requirement set,
  with original task text attached. Extraction variants remain separately measured.
  If that shared extraction is unusable, both semantic probes are explicitly skipped.
- Ruling: generic word boundaries currently reject 6 formerly accepted quotes in
  concatenated browser text. Report this false-rejection tradeoff; do not hide it.

- Review fixes: numeric-token tests and lock/taxonomy/shared-requirement tests RED→GREEN; full suite 75 passed, 2 skipped.
- Live diagnostic: provider translates schema to JSON mode and requires the word
  JSON in the messages; semantic prompt omitted it. Added explicit JSON instruction
  with regression test. One diagnostic attempt got 429, then reproduced 400.
- Ruling: resume in v2 output directory with copied responses, logs and budget;
  exact request fingerprints prevent reusing changed prompts. Preserve original
  probe manifest as provenance. This avoids rebilling 19 completed responses.

- Task 1 complete: 75 tests passed, 2 skipped after review fixes and JSON prompt regression.
- Task 2 complete: 126 completed live responses on six development cases; 151 total
  attempts including 23 rate limits and 2 JSON-mode request errors. Known cost $0.12079626.
- Postprocessing: 21 reviewer ID-string lists deterministically converted to ref
  objects and validated. Raw and repaired metrics reported separately, no paid calls.
- Results and all rulings/caveats exported to READ-ME.txt and the artifact bundle.
- No default harness promotion, integration commit, push or new 72-trial evaluation.
