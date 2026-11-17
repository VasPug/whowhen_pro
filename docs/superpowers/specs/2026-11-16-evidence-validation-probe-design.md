# Evidence validation development probes

User authorized testing all proposed approaches. Compare saved-response matching and
live development-only format/evidence variants; do not silently promote a new policy
into the evaluation harness or overwrite either completed pilot.

Offline: compare exact matching, conservative normalization, task aliases,
ellipsis location, and approximate matching as a diagnostic only. Record original
source spans and distinguish located passages from supported claims. Use all saved
citation objects plus adversarial changes to numbers, negation, qualifiers and step IDs.

Live: use six development cases only, frozen Qwen/Alibaba and existing decoding.
Generate one shared baseline diagnosis per case. For each of four reviewer roles,
compare current prompt, clean quote prompt, clean quote prompt plus JSON schema,
and clean source-ID prompt plus JSON schema. Also compare task requirements and
semantic checks with quote versus source-ID schemas. Up to 126 calls before retries,
shared $5 conservative reservation ceiling, unchanged original experiments.
API errors remain visible; no silent provider/model fallback. No hidden labels in
prompts. Source-ID validity proves source existence, never claim support. Include
manual inspection of recovered quotations and selected live semantic outputs.

Success is evidence/format usability, not improved final F1. Report stage-level
validity, semantic inconclusiveness, rejection causes, tokens/costs. Offline matcher
reprocessing does not recreate final judgments under changed evidence. This is a
bounded development probe, not a new benchmark result.
