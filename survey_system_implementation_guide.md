# Survey Writing System: Implementation Guide

> **Audience:** programming agent (Claude Code, Codex, etc.).
>
> **Read alongside:** `survey_system_design.md` (the architecture document). This guide references its section numbers and does not redefine concepts.
>
> **What this guide is:** the architecture document, sliced into phases that can be delivered independently. Each phase has a clear boundary, deliverables, and acceptance criteria.

---

## 0. How to read and use this guide

- This guide is organized by **phase**. **Implement them in order.** Complete and verify one phase before starting the next.
- Each phase has a "Defer" section listing **what not to do in that phase**. Even if the design document describes a feature, if it appears in Defer, skip it for the current phase.
- The "Acceptance criteria" at the end of each phase is a **hard contract** — the phase isn't done until they all pass.
- When the design document doesn't cover a detail, follow the "Cross-cutting standards" (§12). If ambiguity remains, record your decision in a `DECISIONS.md` deliverable for that phase, so a human can review.
- **Do not attempt to implement all phases in one pass.** Each phase is 1–2 days of focused work.

---

## 1. Tech stack and project conventions

### 1.1 Required choices

- **Python 3.11+**
- **Pydantic v2** for all data-contract validation
- **Typer** for the CLI
- **PyYAML** for config
- **stdlib `logging`** + JSONL run logs (no external logging framework)
- **marker-pdf** for PDF → markdown (see Phase 2)

### 1.2 LLM client abstraction

Do not bind to a single provider. Implement a thin abstraction layer:

```python
# survey_system/llm/client.py
class LLMClient:
    def complete_structured(
        self,
        prompt: str,
        schema: dict,           # JSON Schema for output
        model_tier: str,        # "cheap" | "capable"
        max_tokens: int = 4096,
    ) -> dict: ...
```

Concrete providers (Anthropic, Gemini, OpenAI) are backends. `model_tier` is mapped to a concrete model ID via `config.yaml`. **Op code only calls the abstraction; never import a provider SDK directly from an op.**

Implement one provider in Phase 0 (recommended: Anthropic, since its `tool_use` is the most stable path to structured output). Add a second provider in Phase 8.

### 1.3 Package layout

```
survey_system/
    __init__.py
    config.py             # Loads config.yaml, pydantic settings
    paths.py              # Single source of path computation (do not concat paths in ops)
    io/
        __init__.py
        papers.py         # Reads/writes papers.csv, applies `include` filter
        bib.py            # Reads references.bib (optional consultation)
        kb.py             # Reads/writes papers/<bib_key>/*.{json,md,txt}
        contracts.py      # Pydantic models for every artifact
    pdf/
        __init__.py
        marker_backend.py # Marker integration (Phase 2)
    llm/
        client.py         # Abstraction layer
        anthropic.py      # Concrete backend
        prompts/          # All prompt templates
    ops/
        __init__.py
        parse_pdf.py
        triage.py
        summarize.py
        extract.py
        propose_anchors.py
        propose_outline.py
        assign_section.py
        build_bundles.py
        # Each op module exports one or more op functions
    status.py             # topic_status()
    cli.py                # Typer app
tests/
    fixtures/
        mini_topic/       # 3–5 papers for smoke tests
    test_io.py
    test_ops_*.py
pyproject.toml
README.md
```

**`paths.py` is the single source of paths.** A path like `topics/<name>/papers/<bib_key>/L1.json` is **only** computed in `paths.py`; ops do not concatenate strings. This is the key to supporting custom storage locations later.

### 1.4 Op function signature convention

Every op follows a uniform signature:

```python
def triage(
    topic_path: Path,
    bib_key: str | None = None,    # None means "process all included"
    *,
    force: bool = False,           # Overwrite existing artifact
    dry_run: bool = False,         # Don't write files; return what would happen
) -> OpResult:
    """
    Every op satisfies:
    - No print(), no input()
    - Returns OpResult (structured result with success/skip/failure breakdown)
    - Idempotent: if the artifact exists and force=False, skip
    - Does not call other ops (orchestration belongs to CLI / drivers)
    """
```

`OpResult` lives in `io/contracts.py`:

```python
class OpResult(BaseModel):
    op_name: str
    processed: list[str]    # bib_keys handled successfully
    skipped: list[str]      # bib_keys skipped (artifact already exists)
    failed: list[FailureItem]   # bib_keys that failed, with reason
    artifacts_written: list[Path]
    duration_seconds: float
```

The CLI renders `OpResult` for humans; a UI consumes it as JSON.

### 1.5 Forbidden inside ops

- ❌ `print(...)`, `input(...)`
- ❌ Calling another op (orchestration belongs to the CLI / driver)
- ❌ Concatenating path strings (use `paths.py`)
- ❌ Reading `os.environ` directly (use `config.py`)
- ❌ Silently swallowing schema validation errors (always write to `_review_needed.csv`)

---

## 2. Phase 0 — Project skeleton

### Goal

The repo can be `pip install -e .`'d; the CLI entry point runs `survey --help`; an empty topic is recognized.

### Scope

- Every directory and stub file from §1.3
- `pyproject.toml` listing dependencies: anthropic, pydantic, typer, pyyaml, python-frontmatter
- `survey_system.cli` exposes a Typer app with placeholder commands: `topic init`, `topic status`, `run <op>` (ops don't exist yet — register stubs)
- `survey_system.config.load_config(topic_path)` loads and validates `config.yaml`
- `survey_system.paths` implements every path computation
- `survey_system.io.contracts` contains the Pydantic models needed in this phase: `PaperRow`, `TopicConfig`, `OpResult`, `FailureItem`

### Deliverables

```
pyproject.toml
survey_system/__init__.py
survey_system/cli.py
survey_system/config.py
survey_system/paths.py
survey_system/io/contracts.py
tests/fixtures/mini_topic/papers.csv     # 3 fake rows
tests/fixtures/mini_topic/references.bib # 3 matching entries
tests/fixtures/mini_topic/config.yaml
tests/test_paths.py
tests/test_config.py
```

### Acceptance criteria

- [ ] `pip install -e .` succeeds
- [ ] `survey --help` shows the `topic` and `run` subcommand groups
- [ ] `survey topic status --topic tests/fixtures/mini_topic` prints something basic (even if just "0 ops run yet")
- [ ] Every path function in `paths.py` has a unit test, covering at minimum `papers_dir`, `paper_artifacts_dir`, `schemas_dir`, `bundles_dir`, `runs_dir`, and `pdfs_dir`
- [ ] Loading `mini_topic/config.yaml` succeeds with correct field types

### Defer

- Any LLM call
- Any op implementation
- Async / background execution

---

## 3. Phase 1 — Data contracts & ingestion

### Goal

Given a topic directory, load the full state from `papers.csv` + `references.bib`. Provide a filtered iterator of papers to downstream ops. L0.md files are not yet generated here (that's Phase 2) — the fixture provides hand-written stubs for unit testing.

### Scope

- `io/papers.py`: reads `papers.csv`; filters by `include == yes`; exposes `iter_included(topic_path)`, `get_paper(topic_path, bib_key)`, `set_include(topic_path, bib_key, value, reason)`
- `io/bib.py`: parses `references.bib`; `get_bib_entry(topic_path, bib_key) -> dict`
- `io/kb.py`: reads/writes files under `papers/<bib_key>/`; exposes `read_meta`, `write_meta`, `read_L0`, `write_L1`, etc.
- `io/contracts.py` expansion: `Meta`, `L1Universal`, `L1ByType`, `L2` (a thin str wrapper), etc. The L1 type-specific portion uses a loose `dict[str, Any]` in this phase; Phase 4 tightens it.
- Pydantic models for every artifact type in design §5
- A validator CLI: `survey topic validate --topic <path>` checks that `papers.csv` row count == `.bib` entry count == `pdfs/` file count; prints any inconsistencies

### Deliverables

```
survey_system/io/papers.py
survey_system/io/bib.py
survey_system/io/kb.py
survey_system/io/contracts.py    # Expanded
survey_system/cli.py             # Added validate command
tests/test_io_papers.py
tests/test_io_bib.py
tests/test_io_kb.py
tests/fixtures/mini_topic/pdfs/                         # 3 fake PDFs (empty bytes ok for now)
tests/fixtures/mini_topic/papers/<bib_key>/L0.md        # 3 hand-written markdown stubs
```

### Acceptance criteria

- [ ] `iter_included(topic_path)` returns the rows of `papers.csv` where `include == yes`
- [ ] Marking a fixture paper as `include = no` and iterating again excludes that row
- [ ] The `validate` command detects mismatches like "papers.csv lists X but pdfs/ has no X.pdf"
- [ ] Every contract model round-trips fixture data (read → model → write → read produces the same content)

### Defer

- Any LLM call
- L1 type-specific strict schema (use `dict[str, Any]` for now)
- `_runs/` logging (stderr via stdlib `logging` is sufficient here)
- PDF parsing (Phase 2)

---

## 4. Phase 2 — Round 0 (PDF parsing via Marker) — NEW

### Goal

Running `survey run round0 --topic <path>` produces `papers/<bib_key>/L0.md` for every included paper by feeding `pdfs/<pdf_filename>` through Marker. This is the **first end-to-end pipeline step** and the only one that uses local ML models instead of a remote API.

### Scope

- `pdf/marker_backend.py`: a thin wrapper around the Marker Python API. Lazy-loads Marker models (they're large — ~3–5 GB VRAM, model files cached locally on first use). Exposes:
  ```python
  class MarkerBackend:
      def __init__(self, torch_device: str = "auto", force_ocr: bool = False, use_llm: bool = False): ...
      def convert(self, pdf_path: Path) -> ParsedPdf:
          """Returns ParsedPdf(markdown: str, images: dict[str, bytes], page_count: int)."""
  ```
  Models are loaded lazily on the first `convert()` call and cached on the instance — never load them in module import. A single `MarkerBackend` instance processes many PDFs in one process to amortize the model-load cost.
- `ops/parse_pdf.py`: implements the `parse_pdf` op (design §3.1). Per-paper. Writes `papers/<bib_key>/L0.md` and, if Marker emits images, writes them under `papers/<bib_key>/_images/`.
- `cli.py`: register `run parse-pdf [--bib-key K] [--limit N]` and `run round0` (single-op round; just calls `parse_pdf` on every included paper).
- Marker is an **optional install group** in `pyproject.toml`: `pip install -e ".[marker]"`. Document this in `README.md`. The reason: Marker pulls in PyTorch and several GB of model dependencies; users running tests on contracts/IO logic shouldn't be forced to install it.

### Implementation notes

- **Marker API call (current, as of 2026):**
  ```python
  from marker.converters.pdf import PdfConverter
  from marker.models import create_model_dict
  from marker.output import text_from_rendered

  converter = PdfConverter(artifact_dict=create_model_dict())
  rendered = converter(str(pdf_path))
  markdown, _, images = text_from_rendered(rendered)
  ```
  `markdown` is a string. `images` is a dict mapping filename → PIL image (or bytes, depending on Marker version) — check the Marker version installed and adapt.
- **Configuration is passed via `create_model_dict()` kwargs or environment variables:**
  - `TORCH_DEVICE=cuda` (or `cpu`, `mps`) — set before importing Marker if you want to control device
  - `force_ocr` is a per-conversion flag (passable via Marker's `ConfigParser`)
  - `use_llm=True` enables Marker's optional LLM mode (better tables/equations, extra cost; requires a Gemini or other LLM API key). Off by default in this system.
- **Idempotency:** if `papers/<bib_key>/L0.md` exists and is non-empty and `force == False`, skip. Marker is the slowest non-LLM step in the pipeline; cheap skips matter.
- **Error handling:**
  - PDF not found → `MissingDependencyError("pdfs/<filename> not found")`; the CLI tells the user to add the PDF
  - PDF corrupt / password-protected → catch Marker's exception, write a row to `_review_needed.csv` (`op_name="parse_pdf"`, `issue="marker_failed: <reason>"`), do **not** write L0
  - L0 shorter than `parse_pdf_min_chars` (default 1000) → write L0 anyway (it might still be usable) **and** flag in `_review_needed.csv` for human inspection
  - Any other Marker exception → retry once; if still failing, flag for review
- **Image handling:**
  - Marker emits images keyed by relative filenames (e.g., `_page_3_Figure_1.png`). Write them under `papers/<bib_key>/_images/`.
  - The L0 markdown references images by these relative filenames; do not rewrite the references — the relative path remains valid when L0 and `_images/` are siblings.
- **Memory:** Marker holds models in VRAM/RAM. If processing many papers in one CLI invocation, the same `MarkerBackend` instance must be reused across all papers in that run. **Do not instantiate a fresh `MarkerBackend` per paper** (it reloads the models each time).
- **Logging:** for each paper: log the PDF path, page count, output length (chars), duration. These are useful for debugging slow / failed conversions.

### Deliverables

```
survey_system/pdf/__init__.py
survey_system/pdf/marker_backend.py
survey_system/ops/parse_pdf.py
survey_system/cli.py                              # Expanded
tests/test_pdf_marker_backend.py                  # @pytest.mark.live, runs on a tiny sample PDF
tests/test_ops_parse_pdf.py                       # Mocks MarkerBackend
tests/fixtures/mini_topic/pdfs/<file1>.pdf        # Real (small) PDFs for live test
tests/fixtures/mini_topic/pdfs/<file2>.pdf
tests/fixtures/mini_topic/pdfs/<file3>.pdf
README.md                                          # Updated install instructions for [marker] extra
```

### Acceptance criteria

- [ ] `pip install -e ".[marker]"` succeeds (cuda/cpu detection works without manual intervention on a fresh venv)
- [ ] On a fixture with 3 small PDFs, `survey run round0 --topic tests/fixtures/mini_topic` produces 3 `L0.md` files with plausible content (headings, paragraphs visible)
- [ ] Idempotency: a second run skips all 3 (none re-processed)
- [ ] `--force` re-processes all 3
- [ ] Marking a fixture paper `include = no` and rerunning round0 skips that one
- [ ] Mocked test: when `MarkerBackend.convert` raises, the op writes to `_review_needed.csv` and does **not** create L0; the op returns `OpResult` with that paper in `failed[]`
- [ ] Mocked test: when Marker returns an L0 shorter than `parse_pdf_min_chars`, L0 is written **and** a row goes to `_review_needed.csv`
- [ ] `MarkerBackend` is instantiated exactly once per CLI invocation (verifiable by counting model-load log lines)

### Defer

- Alternative PDF backends (pymupdf4llm, markitdown) — Phase 8
- Equation accuracy tuning via `use_llm=True` — leave off by default
- Parallel PDF conversion — the bottleneck is model loading and VRAM; for a CPU run a sequential pass is fine, and for GPU users a single worker is usually optimal at this scale

### Cost guardrail

Marker is **local compute**, no API spend. On a CPU it's ~30–120 s/paper; on a consumer GPU ~5–15 s/paper. 100 papers ≈ 1–3 hours on CPU, 10–25 minutes on GPU. First run downloads ~1 GB of model weights — warn the user.

---

## 5. Phase 3 — Round 1 vertical slice (triage + L3)

### Goal

Running `survey run round1 --topic mini_topic` generates `meta.json` and `L3.txt` for every included paper. This is the first end-to-end LLM-using pipeline step.

### Scope

- `llm/client.py`: the abstraction layer (§1.2)
- `llm/anthropic.py`: structured output via `tool_use`. **This is the key technical risk;** unit-test it first.
- `llm/prompts/triage.txt`, `llm/prompts/summarize_l3.txt`: prompt templates with placeholders
- `ops/triage.py`: implements `triage()` (design §3.1)
- `ops/summarize.py`: implements `summarize_L3()`
- `cli.py`: register `run triage --topic X [--bib-key K] [--limit N]` and `run round1` (orchestrates triage → summarize_L3)

### Implementation notes

- **Prompt templates** use `string.Template` or f-strings; placeholder names are clear (`{{abstract}}`, `{{intro_first_para}}`). Keep prompts in standalone `.txt` files, not hardcoded in `.py` — that lets a non-programmer tune them later.
- **L0 excerpting:** triage reads only the abstract and the first intro paragraph, not the whole file. Implement `extract_abstract_and_intro(L0_text) -> str` — heuristics: look for `# Abstract` / `# Introduction` markdown headings, or in their absence, take the first 2000 characters. Place this in `io/kb.py`; downstream ops also use it.
- **Structured output:** with Anthropic's `tool_use`, define a tool `record_triage` whose `input_schema` is the JSON schema of `Meta` (paper_type, paper_type_confidence, etc.). Set `tool_choice` to force its invocation. Return the parsed dict.
- **Failure handling:** if the returned `paper_type` is not in the enum (one of 8 values) → retry once; on second failure, write a row to `_review_needed.csv` and write a partial `meta.json` (paper_type left blank, paper_type_confidence = 0, tldr still written if the LLM returned one).

### Deliverables

```
survey_system/llm/client.py
survey_system/llm/anthropic.py
survey_system/llm/prompts/triage.txt
survey_system/llm/prompts/summarize_l3.txt
survey_system/ops/triage.py
survey_system/ops/summarize.py
survey_system/cli.py                    # Expanded
tests/test_llm_client.py                # Mocked
tests/test_ops_triage.py                # Mocked LLM, verifies file output
tests/test_ops_summarize.py
```

### Acceptance criteria

- [ ] With a mocked LLM client, `triage()` over the 3-paper mini_topic produces 3 `meta.json` files matching the `Meta` schema
- [ ] Real LLM call (**use the cheapest model**) on 3 real papers (pick your own) produces sensible `paper_type` and `tldr`
- [ ] **Idempotency:** a second `round1` run skips every paper (unless `--force`)
- [ ] Force a mocked LLM response to return an out-of-enum `paper_type`: assert that `_review_needed.csv` gets a row and `meta.json` has default values
- [ ] Mark a paper `include = no`, re-run round1: that paper is skipped

### Defer

- Concurrency (sequential first; concurrency in Phase 8)
- `_runs/` JSONL logging (stderr is fine here)
- Multiple providers (Anthropic only)
- Any auto-orchestration between ops (CLI does manual sequencing)

### Cost guardrail

Before running round1 for real, **start with `--limit 3`** to validate the prompt. Don't run on 100 papers without checking output quality first. Triage uses the cheap model; 3 papers ≈ $0.01.

---

## 6. Phase 4 — Round 4 vertical slice (extract L1 + L2)

### Goal

Running `survey run round4 --topic <path>` generates `L1.json` and `L2.md` for every included paper. The schema is **provided manually in this phase** — automatic schema design is Phase 7.

### Scope

- `schemas/schema_v1.json` template: contains the universal block + type_specific blocks for the 8 paper_types. **Phase 4 does not implement the schema-design op** — ship a hand-written `schema_v1.json` as a mini_topic fixture.
- `io/schemas.py`: loads and validates the schema file; reads current version (from `schemas/current.txt`); selects the appropriate sub-schema by paper_type
- `ops/extract.py`: `extract_L1()` (design §3.1)
- `ops/summarize.py`: expand with `summarize_L2()`
- `llm/prompts/extract_universal.txt`, `extract_by_type/*.txt`: one prompt per paper_type
- `cli.py`: register `run extract`, `run summarize-l2`, `run round4`

### Implementation notes

- **The schema is two parts:** universal + type_specific. At runtime, take the paper's `meta.paper_type`, pick the corresponding sub-schema, and assemble a complete `input_schema` for `tool_use`.
- **L0 is passed in full.** If L0 exceeds 100k tokens, truncate to 80k (leaving prompt/output room) and append a row to `_review_needed.csv` ("L0 truncated").
- **Write `_schema_version`** at the top level of every `L1.json`. Future schema upgrades use it to know which papers need re-extraction.
- **L2 generation:** `summarize_L2(bib_key)` reads L1 + optionally L0. **Try with L1 alone first** — if quality is acceptable, skip L0 to save tokens; if it isn't, add L0.

### Deliverables

```
survey_system/io/schemas.py
survey_system/ops/extract.py
survey_system/ops/summarize.py                       # Expanded with L2
survey_system/llm/prompts/extract_universal.txt
survey_system/llm/prompts/extract_by_type/method.txt
survey_system/llm/prompts/extract_by_type/survey.txt
survey_system/llm/prompts/extract_by_type/benchmark.txt
survey_system/llm/prompts/extract_by_type/dataset.txt
survey_system/llm/prompts/extract_by_type/analysis.txt
survey_system/llm/prompts/extract_by_type/position.txt
survey_system/llm/prompts/extract_by_type/application.txt
survey_system/llm/prompts/extract_by_type/tool_system.txt
survey_system/llm/prompts/summarize_l2.txt
tests/fixtures/mini_topic/schemas/schema_v1.json    # Hand-written
tests/fixtures/mini_topic/schemas/current.txt       # Contains: "v1"
tests/test_ops_extract.py
tests/test_io_schemas.py
```

### Acceptance criteria

- [ ] Running `extract` on one mini_topic paper produces an `L1.json` that validates against schema_v1's matching sub-schema
- [ ] Calling `extract` on a paper without `meta.json` (i.e., Round 1 not yet run) raises an error and does not write L1 (dependency check)
- [ ] `_schema_version` is at the top level of every produced `L1.json`
- [ ] L2.md word count falls in 100–400 (warn at log level if outside; soft bound)
- [ ] Idempotency: a second `extract` run skips everything
- [ ] Real run on 3 papers — **manually inspect** the L1.json content for plausibility

### Defer

- Automatic schema design (Phase 7)
- L1 schema upgrade path (no `schema_v2` migration logic yet)
- Anchor-aware "spotlight" tagging (L1 doesn't know about anchors; spotlights are a bundle-stage concern)

### Cost guardrail

Extract is the cost-concentrated op. Try `--limit 3` first; capable-model cost per paper is ~$0.10–$0.30. Validate prompt quality before running on 100 papers.

---

## 7. Phase 5 — Round 5+6 (outline + assign + bundle)

### Goal

Run `survey run round5 --topic <path>` → human picks an outline → run `survey run round6 --topic <path>` → get `bundles/section_*.md` files ready to paste into Claude for drafting.

**This is the MVP completion point.** A user can go from 100 papers to a working set of writing bundles.

### Scope

- `ops/propose_outline.py`: `propose_outline()` (design §3.2). **Anchor weighting uses a placeholder for now** — `anchors.csv` may not exist this phase, so the weighting step is skipped; anchor flagging arrives in Phase 6.
- `ops/assign_section.py`: `assign_section()` (per-paper op)
- `ops/build_bundles.py`: `build_bundles()` (script-only, no LLM)
- `llm/prompts/propose_outline.txt`, `llm/prompts/assign_section.txt`
- `cli.py`: register the three op commands + `run round5` (only `propose_outline`) + `run round6` (assign → bundle). **Round5 → human picks outline → round6** is not one chain; it must be two CLI invocations.
- `outline.md` parsing: bundle generation needs to extract the section list from the human-edited `outline.md`. Convention: section names are H2/H3 headings; section path looks like `"3. Dynamic Detection"` or `"3.2 Subsection Name"`.

### Implementation notes

- **propose_outline input construction:** read every included paper's L3 + year/venue from `papers.csv` + `meta.paper_type`. Concatenate into one text block as prompt input. 100 papers × (~30-word L3 + meta) ≈ 5–8k tokens — comfortable.
- **outline_candidates_v{n}.md output:** ask the LLM for markdown with 3 candidates separated by H1, H2/H3 chapter tree underneath each. After the tree, an H2 "Trade-offs" paragraph. Write the LLM output **straight to disk** without strict schema validation — markdown is free-form.
- **outline.md parsing:** use a simple markdown parser (`markdown-it-py` or a hand-rolled H2/H3 walker). Every leaf heading (deepest header) is a section path. Slugify to `{number}_{slug}`, e.g., `3_2_dynamic_detection`.
- **assign_section:** single-paper input is L2 + full outline.md + paper meta. The LLM returns structured output: `primary_section_path`, `secondary_section_paths: list[str]`, `confidence`, `reason`. `primary_section_path` **must** appear in the parsed outline's section list — if not, that's a failure, write a review row.
- **build_bundles** (pure script):
  1. Parse outline.md to get the section list
  2. Read section_assignments.csv
  3. For each section: collect papers with primary == this section (sort by year asc, anchors first); papers with secondary == this section go in a separate "Cross-references" block (title + bib_key only)
  4. For each paper, read full L2.md, and pull `universal` + "key fields" from `type_specific` (see below)
  5. Assemble per the bundle format in design §5
- **"Key L1 fields" subset:** each paper_type has a set of fields that should appear inline in bundles. In each by_type sub-schema in `schema_v1.json`, add a non-standard property `_bundle_fields: list[str]` listing 1–4 most relevant field names. For example, `method` papers might have `_bundle_fields: ["method_idea", "datasets", "main_results"]`. Bundle generation reads this list and inlines those fields.

### Deliverables

```
survey_system/ops/propose_outline.py
survey_system/ops/assign_section.py
survey_system/ops/build_bundles.py
survey_system/io/outline.py              # outline.md parsing
survey_system/llm/prompts/propose_outline.txt
survey_system/llm/prompts/assign_section.txt
survey_system/cli.py                     # Expanded
tests/fixtures/mini_topic/outline.md     # Hand-written for testing
tests/test_io_outline.py
tests/test_ops_propose_outline.py
tests/test_ops_assign_section.py
tests/test_ops_build_bundles.py
```

### Acceptance criteria

- [ ] `propose_outline` on mini_topic produces `outline_candidates_v1.md` with at least 2 candidates, each containing a Trade-offs paragraph
- [ ] outline.md parsing correctly extracts the section-path list
- [ ] `assign_section` writes one row of the assignments CSV per included paper, and the `primary_section` always matches a known outline section
- [ ] `build_bundles` produces `bundles/section_*.md` files that render correctly in a markdown viewer
- [ ] Each bundle contains, per paper: bib_key, full L2, key L1 fields; anchor papers (if tagged) come first (Phase 5 can sort all by year if anchors are absent)
- [ ] End-to-end: mini_topic from `papers.csv` → bundles runs cleanly

### Defer

- Anchor weighting (Phase 6)
- Side-by-side outline-candidate comparison UI
- Figures/complex structures in bundles (keep them plain markdown)

### Cost guardrail

`propose_outline` once ≈ $0.50; `assign_section` × 100 ≈ $1–2. Round5+6 total ≈ $3.

---

## 8. Phase 6 — Round 2 (anchor recommendation)

### Goal

Run `survey run round2 --topic <path>` → produce `anchors_candidates_v1.csv` → human fills `your_decision` → run `survey topic curate-anchors --topic <path>` to promote selected rows to `anchors.csv`. Downstream outline and bundle ops then weight by anchors.

### Scope

- `ops/propose_anchors.py` (design §3.2)
- `io/anchors.py`: read anchors_candidates / anchors.csv
- `cli.py`: `run anchors`, `topic curate-anchors` (copies rows where `your_decision == yes` to anchors.csv, adding a `role_notes` column)
- Modify Phase 5's `propose_outline` and `build_bundles`:
  - In the `propose_outline` prompt, tag anchor papers with "(ANCHOR)" and add an instruction "the outline must cover anchors well"
  - In `build_bundles`, sort anchors first in each section and split the section into "Anchor papers in this section" / "Other papers" subheadings

### Acceptance criteria

- [ ] `propose_anchors` outputs a CSV with venue_tier, llm_score, llm_reason, is_survey, suggested columns
- [ ] The `venue_tier` map in `config.yaml` is correctly applied via string match
- [ ] `curate-anchors` copies the `yes`-marked rows to anchors.csv without touching anything else
- [ ] When `anchors.csv` exists, `build_bundles` output distinguishes "Anchor papers" from "Other papers"
- [ ] When `anchors.csv` is absent, `build_bundles` still works (backward compatible)

### Defer

- Citation-graph signals
- Auto-generated `role_notes` (always human-filled)

---

## 9. Phase 7 — Round 3 (automatic schema design)

### Goal

`survey run round3 --topic <path>` reads anchors → produces `schemas/schema_v{n+1}.json` candidate → human reviews → write `current.txt` to bump the version. Round 4 then re-extracts affected papers under the new schema.

### Scope

- `ops/design_schema.py` (design §3.2)
- `io/schemas.py` expansion: version management, writing `current.txt`, computing schema diffs
- `cli.py`: `run schema-design`, `topic promote-schema --version vN`, `run extract --since-schema vN` (only re-extracts papers with `_schema_version < vN`)

### Acceptance criteria

- [ ] `design_schema` reads L0 for each anchor in `anchors.csv` (note: total tokens may exceed the capable model's context — **implement chunk-and-aggregate**: process anchors in groups of 5, then merge)
- [ ] Output `schema_vN.json` candidate includes `_provenance` (design §5)
- [ ] `extract --since-schema vN` only processes papers whose L1 has `_schema_version != "vN"`

### Defer

- Fully automatic schema-upgrade triggers (keep human-promoted)
- GUI schema diff (CLI JSON diff is fine)

---

## 10. Phase 8 — Polish

### Goal

Make the system suitable for long-term use: logging, status queries, concurrency, review-queue management.

### Scope

- `_runs/{op}_{timestamp}.log` JSONL logging: one line per op invocation (start, end, processed, failed, cost)
- `status.py` full implementation: returns a dict with per-round completion percentage, pending review items, recent op runs
- `cli.py`: `topic status --detailed` shows a per-round completion table
- `survey review --topic <path>`: interactive walk of `_review_needed.csv` (CLI accepts y/n/skip; does **not** break UI-readiness — the review CSV is still externally editable)
- Per-paper op concurrency: `triage`, `extract`, `summarize`, `assign_section` accept `--workers N`. **`parse_pdf` does not get this flag** — Marker's bottleneck is VRAM, and parallel conversion typically saturates a single GPU already.
- Second LLM provider (Gemini or OpenAI), verifying the `LLMClient` abstraction
- Alternative PDF backend (optional): pluggable in `pdf/` as `pymupdf_backend.py`, selected via config. Faster and lighter than Marker for digital PDFs without complex tables/equations.

### Acceptance criteria

- [ ] After a round1 run, `_runs/` contains JSONL logs you can `cat` to see structured records
- [ ] `topic status` prints a table showing per-round completion for mini_topic
- [ ] `--workers 4` on `extract` is measurably faster than `--workers 1` (even on a small fixture)
- [ ] Switching to the second LLM provider, re-running round1 on one paper produces structurally valid output

### Defer

- A real UI (forever future)
- Distributed / cluster execution
- Provider-specific optimizations (e.g., Anthropic prompt caching)

---

## 11. Cross-cutting standards

### 11.1 Paths

Every path goes through `survey_system.paths`. Op code never concatenates strings. When adding a new artifact type, **first** add a path function in `paths.py`, then use it.

### 11.2 Error handling

Inside an op, errors split into three categories:

- **Input error** (missing meta.json, missing L0, missing PDF, etc.) → raise `MissingDependencyError`; the CLI catches and prints "run X first"
- **External-tool error** (LLM API failure, schema validation failure, Marker exception) → retry once, then write to `_review_needed.csv` and continue with the next paper
- **System error** (IO failure, unexpected exception) → raise; the CLI top-level catches and reports

### 11.3 LLM call conventions

- Before and after each LLM call, `logging.info` records the model_tier, estimated input/output tokens, and bib_key
- Actual token counts and cost come from the API response and go into the run log
- Prompt templates use `{{var}}` placeholders, rendered via `string.Template` or jinja2. Templates and code are separate files.

### 11.4 Testing

- Each op has at least two tests: a **mocked-LLM test** (verifying IO and schema validation) and a **real-LLM smoke test** marked `@pytest.mark.live` (excluded from CI)
- For Phase 2, also a `@pytest.mark.live` Marker test that converts one small fixture PDF and checks the output is non-empty markdown with at least one heading
- The mini_topic fixture stays at 3–5 papers, small enough that a real-LLM full run is < $1 and a real-Marker full run is < 10 minutes on CPU

### 11.5 Documentation sync

After each phase, update `README.md`'s "Currently supports:" list. A human user should be able to read the README and know which features are available now.

---

## 12. First step

Before starting Phase 0, do one thing: **create `DECISIONS.md` at the repository root** and record key decisions as you go ("used Typer over Click because...", "used jinja2 over string.Template because...", "pinned marker-pdf to version X because..."). This is the trail for future-you and for human reviewers — better than commit messages for architectural decisions.

Then proceed Phase 0 → 8 in order. After each phase, stop and let a human verify on mini_topic before moving on. **Resist the urge to write all phases in one pass.**
