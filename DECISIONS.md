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
