# Source-ID harness integration

User approved the tested shared evidence approach and requested integration and
updated scores. Apply clear role instructions, source IDs, and deterministic parsing
to AgentRx and RAFFLES. Preserve their distinct call workflows and original baseline.

A shared reference resolver accepts an exact source ID string or an object with ref,
retrieves original source text, ignores model-supplied quote/extra fields, and rejects
missing, malformed, unknown or future IDs. Source existence is not semantic support.
Semantic/reviewer conclusive outputs require at least one valid reference. Unsupported
outputs become inconclusive with warnings. Full source text is audit evidence; bounded
logs and compact reviewer histories prevent redundant context inflation.

Requirements explicitly prioritize the main task objective before presentation rules,
within existing caps. Requirements and constraint sources use IDs. Numeric operands
retain strict source-span/value checks; do not loosen numerical safety. Reviewer
prompts contain task, recorded sources, taxonomy and candidate, without baseline
instructions that conflict with the review contract. Request schemas for requirements,
semantic checks and reviewers; still accept deterministic equivalent ID representations.

Keep Qwen/Alibaba, decoding, 24 evaluation cases, taxonomy, scoring and budget unchanged.
Validate full workflows on the six existing development cases under a separate $5
ceiling, then freeze code and execute a new 72-trial evaluation under its existing
$25 ceiling. Do not overwrite old runs or portray this inspected cohort as held-out.
Report actual F1, other metrics, paired uncertainty, validation warnings and cost.
