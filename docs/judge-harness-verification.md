# Verification and implementation decisions

Verified on 2026-11-15 in the prepared Python 3.12 environment. No paid model requests were made.

## Evidence

- Full local suite: **45 passed, 2 skipped**. The skipped tests are upstream tests requiring all dataset modalities; this pilot downloads text only.
- Exact baseline prompt parity checked across **all 6,257 released text traces**, covering eight frameworks.
- Original scorer round-trip checks passed on representative traces from all eight text frameworks; the accepted-alternative-label case passed separately.
- Real pinned data prepared: **24 evaluation cases + 6 disjoint development task groups**. The release has 17 taxonomy modes; 14 occur in its text split, and nine occur in this pilot sample.
- Default selection contains six examples each from macnet, magentic-one, mathchat, and smolagents. The short-input limits leave 1,110 eligible task groups; 4,015 rows exceed the source-character limit and 445 exceed the step limit. Remaining duplicates are collapsed by task group before sampling.
- Full offline launcher run: **72/72 condition–case outcomes completed**, using 387 synthetic calls (24 baseline, 123 AgentRx, 240 RAFFLES). These are plumbing tests, not model performance results.
- Repeating the launcher reused results without new synthetic calls. Offline and live stores remain separate; no live result directory was created.
- `doctor` verified the final prepared inputs, frozen identity, model/provider settings, and absence of an API key.
- The public OpenRouter endpoint listing advertised Qwen3.5-122B-A10B on Alibaba, seed/reasoning/output limits, and the configured input/output prices. Authenticated completion compatibility remains untested until a key is supplied.

## Independent review

A separate reviewer inspected the whole implementation and reproduced five material issues. Each was turned into a failing regression, corrected, and included in the final passing suite:

1. Invalid account/key/routing errors now stop scheduling without caching terminal case outcomes; key preflight uses a nonbillable endpoint.
2. Numeric citations are validated against whole numeric tokens in original source text, including negative signs, Unicode minus, grouped numbers and scientific notation. Unsupported/ambiguous formats must use semantic checking.
3. Prepared cohort membership, framework/group metadata, and case/label fingerprints are bound into the run identity. Counts, uniqueness, partition disjointness and references are validated.
4. Attempt-start records persist before transport; unfinished attempts are reported with unknown outcome/usage.
5. Transient error payloads and HTTP error statuses share the retry policy.

The fixes were verified with regression tests rather than a second independent review. No material review finding was left unresolved.

## Rulings made during unattended work

- Implement directly with a final independent review: the user authorized planning followed by implementation while away. This avoids another approval pause but means implementation choices below were selected by the assistant.
- Use a text-only 24-case pilot, six separate development groups, one repetition, and a fixed OpenRouter Alibaba endpoint. This makes a single-key run practical; it cannot establish multimodal or full-benchmark performance.
- Use the pinned released 17-mode taxonomy rather than the paper description's 18-mode count. This preserves internal scoring consistency at the cost of not reproducing that paper version exactly.
- Preserve baseline-visible input information and original scoring semantics, including partial-field scoring and canonical F1 versus accepted alternatives. Changing them would change the comparison; their limitations remain part of the experiment.
- Keep strict malformed-intermediate-output handling and terminal case-specific failures. This prevents silent repair/selection but can lower completion rates; reports expose those rates. Global setup/account errors are resumable instead of case failures.
- Keep the feature branch and worktree available, without pushing or merging. The requested runnable environment is ready locally; repository integration is a separate action.
- Use explicit ledger/task checks because the cloud skill's helper-script resource could not be read. This changes process tooling only, not experiment behavior.

## Remaining boundaries

Multimodal coverage, full-paper reproduction, compute-matched comparisons and independently verified hosted checkpoint immutability are outside the initial pilot. A real key is still required to establish authentication, returned provider/model metadata, and Qwen's compliance with the requested output formats.

The lockfile is installed in the prepared environment. The launcher checks dependency availability rather than forcibly replacing packages in an already-populated virtual environment; use the quickstart's lockfile-install command if deliberately reusing a different environment. This was recorded as reproducibility polish, not a blocker in the delivered environment.
