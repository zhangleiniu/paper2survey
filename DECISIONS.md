# Decisions

## Phase 1

- `L1ByType` is intentionally loose and uses `dict[str, Any]` for this phase. Strict type-specific L1 schemas are deferred until schema design work lands.
- Phase 1 performs no LLM calls. It only loads, validates, filters, and writes file-backed topic state.
- BibTeX parsing is dependency-free for now and covers the simple curated fixture format used by the ingestion tests.

## Phase 2

- Marker models are lazy-loaded inside `MarkerBackend.convert()` so importing the package or running non-PDF tests does not allocate model memory.
- A single `MarkerBackend` instance is reused for every paper in a `parse_pdf` or `round0` invocation.
- PDF parsing is idempotent: existing non-empty `L0.md` files are skipped unless `--force` is passed.
- Marker conversion failures are retried once. A second failure is recorded in `_review_needed.csv`.
- Short L0 outputs are still written, then flagged for review using `marker.parse_pdf_min_chars`.

## Phase 3

- Round 1 excerpting looks for `# Abstract` and `# Introduction` markdown headings, then uses the abstract plus the first introduction paragraph. If headings are absent, it falls back to the first 2000 characters.
- Anthropic structured output is forced through `tool_use` with the requested JSON schema as the tool input schema. The provider backend returns the tool input dict to the generic `LLMClient`.
- Model tiers are resolved from `config.yaml`; operation-specific keys such as `triage` and `summarize` can override the generic `cheap` and `capable` tiers.
- If triage returns an out-of-enum `paper_type`, the op retries once. A second invalid response writes partial `meta.json` with `paper_type = null`, confidence `0`, preserves any returned TLDR/topics, and appends `_review_needed.csv`.
- Live LLM tests are opt-in with `RUN_LLM_LIVE=1` so normal tests stay deterministic and offline.

## Phase 4

- Schema design remains manual. Phase 4 reads `schemas/current.txt` and the matching `schema_vN.json`; automatic schema proposal and promotion stay deferred.
- L1 validation uses the small JSON Schema subset used by our topic schemas: object, array, string, number, integer, boolean, required fields, enum/const, and `additionalProperties`.
- Extraction fills `_schema_version` and `_paper_type` in code before validation, so the LLM focuses on the universal and type-specific content.
- Extraction retries once after schema validation failure, then appends `_review_needed.csv` and leaves `L1.json` unwritten.
- L2 summarization uses L1 only in this phase to save tokens. It writes the narrative even if it falls outside the 100-400 word soft bound, then flags the paper for review.

## Phase 5

- Round 5 and Round 6 are deliberately separate. The user chooses and edits `outline.md` between candidate generation and section assignment.
- Outline parsing is a hand-rolled H2/H3 walker. H3 headings are leaf sections; H2 headings become sections only when they have no H3 children. The `Trade-offs` heading is ignored as outline structure.
- Section assignment accepts only primary section paths that exactly match parsed `outline.md` paths. Invalid primary paths are logged to `_review_needed.csv`.
- Bundles are plain markdown files, one per parsed section. They contain anchor papers first, then other primary papers sorted by year, followed by cross-references for secondary assignments.
- Bundle key fields come from the current schema's non-standard `_bundle_fields` list for each paper type, plus the universal L1 block.

## Phase 6

- `anchors_candidates_v1.csv` is the human review surface. It contains paper metadata, venue tier, LLM score/reason, `is_survey`, deterministic `suggested`, `your_decision`, and optional `role_notes`.
- Venue tier is an exact match against `config.yaml:venue_tiers`; missing venues default to tier 3.
- The deterministic suggestion rule is: suggest surveys, plus tier-1 papers with `llm_score >= 4`.
- Curation only promotes rows where `your_decision == yes` into `anchors.csv`. `role_notes` is copied when present, otherwise the LLM reason is used.
- Downstream anchor weighting remains file-based: if `anchors.csv` exists, outline prompts add `(ANCHOR)` tags and bundles split anchor papers before other papers.
