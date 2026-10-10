# Instructions for coding agents working in this rulebook

This repository is the Niyam rulebook: Maharashtra welfare scheme eligibility
rules as tested code. Every rule must trace back to an official government
document. Wrong rules can stop people from receiving money they are owed.

## Layout
- `schemes/<state>/<scheme>.yaml`: conditions and benefit. Every condition has `valid_from`, optional `valid_until`, and a `source` (doc, page, clause, quote, quote_en).
- `parameters/<state>/<scheme>/<name>.yaml`: dated values in OpenFisca format. Each value has `metadata.reference` (doc, page, clause, quote, quote_en).
- `tests/<state>/<scheme>.yaml`: test citizens. Each case has `date`, `person`, `expect` and `source`.
- `sources/index.yaml` and `sources/<state>/<code>.pdf`: the official documents.
- `glossary/maharashtra.md`: how recurring legal phrases are interpreted.
- `docs/FORMAT.md`: the file format with a complete example. Read it before creating a new scheme.
- `schema/person.yaml`: the only facts rules may use. Never add personal identifiers.

## Rules for every change
1. Never edit or delete history. To change a parameter, add a new dated value. To change a condition, set `valid_until` on the old one (the day before the change) and add a new condition with the same `id` and a new `valid_from`. To remove a condition, only set `valid_until`.
2. Every new value and condition must have a source with the exact quote from the document, its page and clause.
3. Add the source document to `sources/index.yaml` (and the PDF to `sources/<state>/`).
4. For every change add at least three test cases dated after the change: just below, at, and just above each limit, plus one case dated before the change showing the old rule still applies.
5. Run `python -m niyam_rulebook test` and do not stop until it prints `0 failed` and no PROBLEM lines.
6. Add a plain-language entry at the top of `CHANGELOG.md` in English, Hindi and Marathi.
7. Only edit files inside `schemes/`, `parameters/`, `tests/`, `sources/`, `glossary/`, `schema/` and `CHANGELOG.md`.
8. Rule expressions may only use `person.<field>`, `params.<name>`, comparisons, `and`, `or`, `not`, arithmetic, lists, and `min`, `max`, `abs`, `len`.

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->
