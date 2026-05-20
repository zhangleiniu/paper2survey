# Decisions

## Phase 1

- `L1ByType` is intentionally loose and uses `dict[str, Any]` for this phase. Strict type-specific L1 schemas are deferred until schema design work lands.
- Phase 1 performs no LLM calls. It only loads, validates, filters, and writes file-backed topic state.
- BibTeX parsing is dependency-free for now and covers the simple curated fixture format used by the ingestion tests.
