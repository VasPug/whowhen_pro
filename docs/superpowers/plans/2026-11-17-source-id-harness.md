# Source-ID Harness Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in the existing worktree.

**Goal:** Integrate tested source-ID evidence handling, validate, and produce corrected pilot scores.
**Architecture:** Shared resolver and output schemas; replace intermediate quote contracts,
keep numeric grounding and final upstream parser/scorer unchanged. Audit source text,
compact references in follow-up prompts. Development smoke test precedes new pilot.
**Tech Stack:** Existing Python/OpenRouter/pytest implementation.
**Spec:** docs/superpowers/specs/2026-11-17-source-id-harness-design.md

## Global Constraints
Frozen Qwen/Alibaba and existing decoding/cohort/scoring. No hidden labels in model
inputs. Preserve old artifacts. Development ceiling $5; evaluation ceiling $25.

## Review Focus
Unknown/future IDs; ignored fabricated quote text; empty evidence cannot cause
consensus; numeric operands still exact; expanded evidence cannot overflow context;
reported usability must not be described as semantic correctness.

### Task 1: Integrate contracts
- [x] RED tests for string/object IDs, unknown/future IDs, retrieved original text,
  conclusive empty-evidence rejection and clean reviewer instructions.
- [x] Implement shared resolver, schemas and ID-first intermediate prompts.
- [x] Preserve numeric guards and baseline parity; run full suite GREEN.

### Task 2: Verify and execute
- [x] Independent scoped review; fix material findings with regression tests.
- [x] Six-case development smoke test of complete harness workflows; inspect warnings.
- [x] Freeze source; prepare and verify same 24-case cohort/config; run 72 live trials.
- [x] Check metrics and resource audit, export results/code, document limitations.

## Progress
- Existing isolated codex/judge-harness worktree reused with earlier edits intact.
- User authorized implementation and scoring; no additional permission gate.

## Completion evidence
- Full test suite: 114 passed, 2 skipped. Independent review found no material blockers; both suggested coverage additions were implemented.
- Development: 18/18 complete, 101 calls, $0.06686264. One genuinely malformed semantic assessment was safely recorded as inconclusive.
- Evaluation run `20439687896ad176`: 72/72 complete, 403 calls, $0.27024062; no transport errors, unknown costs, or JSON/citation validation warnings.
- Independent macro-F1 recomputation from predictions and canonical labels matches the report; saved per-axis scores were rechecked with the unchanged upstream scorer and aggregates verified separately.
- What macro-F1: baseline 15.4321%, AgentRx 20.9091%, RAFFLES 20.1852%. No confirmatory improvement claim: same previously inspected 24-case short-text cohort.
- Source and result archives exported under `/workspace/artifacts/`.
