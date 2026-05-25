# Survey System

A file-backed pipeline that turns a folder of PDFs into structured writing bundles for academic survey papers. It manages four granularity levels per paper (full text → structured fields → narrative summary → one-sentence card) so that every LLM call sees "just enough" context regardless of corpus size.

## Install

```bash
uv sync          # base install (no PDF parsing)
uv run survey --help
uv run pytest
```

PDF parsing (Marker) requires local ML models (~3–5 GB VRAM or CPU) and is an optional extra:

```bash
uv sync --extra marker
```

---

## Setting up a topic

A **topic** is a directory you create and manage. The system reads from it and writes derived artifacts back into it.

### Required directory layout

```
my_topic/
    papers.csv        ← one row per paper (you fill this)
    references.bib    ← BibTeX entries (you fill this)
    config.yaml       ← model and venue config (you fill this)
    pdfs/
        author2024title.pdf   ← PDFs, named however you like
        ...
```

### `papers.csv`

One row per paper. The `bib_key` column is the primary key and must exactly match a BibTeX entry key in `references.bib`.

| Column | Required | Description |
|---|---|---|
| `bib_key` | yes | Primary key — must match a key in `references.bib` and is used in `\cite{}` |
| `title` | yes | Paper title |
| `year` | yes | Publication year |
| `venue` | yes | Conference or journal name — must match the `venue_tiers` map in `config.yaml` |
| `pdf_filename` | yes | Filename (with extension) under `pdfs/` |
| `include` | yes | `yes` or `no` — only `yes` rows are processed by any pipeline op |
| `exclusion_reason` | no | Free text, filled when `include = no` |
| `user_notes` | no | Optional notes |

Example:

```csv
bib_key,title,year,venue,pdf_filename,include,exclusion_reason,user_notes
brown2020gpt3,Language Models are Few-Shot Learners,2020,NeurIPS,brown2020gpt3.pdf,yes,,Foundational LLM paper
wei2022cot,Chain-of-Thought Prompting,2022,NeurIPS,wei2022cot.pdf,yes,,
ouyang2022rlhf,Training language models to follow instructions,2022,NeurIPS,ouyang2022rlhf.pdf,no,off-topic,
```

### `references.bib`

A standard BibTeX file. Every `bib_key` in `papers.csv` must have a matching entry here.

```bibtex
@article{brown2020gpt3,
  title   = {Language Models are Few-Shot Learners},
  author  = {Brown, Tom and others},
  year    = {2020},
  journal = {NeurIPS}
}

@article{wei2022cot,
  title   = {Chain-of-Thought Prompting Elicits Reasoning in Large Language Models},
  author  = {Wei, Jason and others},
  year    = {2022},
  journal = {NeurIPS}
}
```

The system never modifies this file. It is used as-is by the LaTeX toolchain.

### `config.yaml`

```yaml
topic_name: my_survey_topic

# Map venue names to tiers (exact string match against papers.csv:venue).
# Missing venues default to tier 3.
venue_tiers:
  NeurIPS: 1
  ICML: 1
  ICLR: 1
  AAAI: 2
  arXiv: 3

# LLM model IDs. Provider is anthropic (default), openai, or vertexai.
models:
  provider: anthropic
  cheap: claude-haiku-4-5-20251001
  capable: claude-sonnet-4-6
  # Per-operation overrides (optional):
  triage: claude-haiku-4-5-20251001
  extract: claude-sonnet-4-6
  summarize: claude-haiku-4-5-20251001
  schema_design: claude-sonnet-4-6
  outline: claude-sonnet-4-6
  assign: claude-haiku-4-5-20251001

# Vertex AI settings, only used when models.provider is vertexai.
# These may be omitted if GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are set.
vertexai:
  project: my-project-id
  location: global

# Quality thresholds — items below these values go to _review_needed.csv.
thresholds:
  triage_confidence_review_below: 0.7
  assign_confidence_review_below: 0.7
  parse_pdf_min_chars: 1000   # L0 shorter than this triggers review

# PDF parsing. Use pymupdf for fast text-only extraction, marker for richer layout/table parsing.
marker:
  torch_device: auto    # auto | cpu | cuda | mps
  force_ocr: false      # true = OCR every page even on digital PDFs
  use_llm: false        # true = Marker's LLM-assisted mode (extra API cost)
  save_images: false    # true = save extracted images under papers/<bib_key>/_images/
  backend: marker       # marker (richer, slower) | pymupdf (faster text extraction)
```

### `pdfs/`

Place your PDF files here. The filenames must match the `pdf_filename` column in `papers.csv`. Any naming convention works; human-readable is recommended.

### Validate the setup

```bash
uv run survey topic validate --topic my_topic
```

This checks that `papers.csv` and `references.bib` have matching keys and that every `pdf_filename` exists under `pdfs/`.

---

## Pipeline

The pipeline has seven rounds. **Run them in order.** Each round is idempotent — rerunning skips already-completed papers unless you pass `--force`. The human gate after each round is described inline.

```
Round 0  PDF → markdown (local ML model, no API)
Round 1  Classify + summarise each paper (cheap LLM)
Round 2  Identify anchor papers (capable LLM + human review)
Round 3  Design extraction schema (capable LLM + human review)
Round 4  Deep extraction + narrative summaries (capable LLM, main API cost)
Round 5  Propose outline structure (capable LLM + human picks one)
Round 6  Assign papers to sections, build writing bundles
Round 7  Write each section (manual, in a chat interface)
```

For Anthropic, set `ANTHROPIC_API_KEY` for Rounds 1–6. For OpenAI, set `OPENAI_API_KEY` and `models.provider: openai` in `config.yaml`.

For Vertex AI, authenticate with Application Default Credentials before running LLM-backed rounds:

```bash
gcloud auth application-default login
```

Then use Vertex AI Gemini model IDs and project settings in `config.yaml`:

```yaml
models:
  provider: vertexai
  cheap: gemini-3.5-flash
  capable: gemini-3.5-flash

vertexai:
  project: my-project-id
  location: global
```

If `vertexai.project` or `vertexai.location` is omitted, the backend falls back to `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.

---

### Round 0 — PDF parsing

Converts each `pdfs/<pdf_filename>` into `papers/<bib_key>/L0.md` (full-text markdown).

For fast text-only extraction, set `marker.backend: pymupdf` in `config.yaml`. For richer layout/table extraction, set `marker.backend: marker` and install Marker (`uv sync --extra marker`).

```bash
uv run survey run round0 --topic my_topic
```

Single paper or limited run:

```bash
uv run survey run parse-pdf --topic my_topic --bib-key brown2020gpt3
uv run survey run round0 --topic my_topic --limit 5
uv run survey run round0 --topic my_topic --force   # re-parse even if L0 exists
```

**Cost:** local compute only, no API. ~30–120 s/paper on CPU, ~5–15 s/paper on GPU. First run downloads ~1 GB of model weights.

**Human gate:** skim a few `L0.md` files to confirm tables and equations parsed correctly. Papers flagged in `_review_needed.csv` may need a better PDF or `--force_ocr`.

---

### Round 1 — Triage and one-sentence cards

Classifies each paper by type and writes a one-sentence summary:

- `papers/<bib_key>/meta.json` — `paper_type`, `paper_type_confidence`, `tldr`, `topics[]`
- `papers/<bib_key>/L3.txt` — one-sentence card (~30 words)

Paper types: `survey`, `method`, `benchmark`, `dataset`, `analysis`, `position`, `application`, `tool_system`.

```bash
uv run survey run round1 --topic my_topic
uv run survey run triage --topic my_topic --bib-key brown2020gpt3
uv run survey run triage --topic my_topic --limit 3 --force
```

**Cost:** cheap model, ~$0.01 for 3 papers. Run `--limit 3` first to validate prompt quality.

**Human gate:** check the paper-type distribution. Mark clearly off-topic papers `include = no` in `papers.csv` — Round 1 is the natural first moment for exclusion.

---

### Round 2 — Anchor paper recommendation

Recommends the 5–15 most important papers (anchors) based on L3 cards, venue tier, and LLM scoring. Anchors are used to design the extraction schema, weight the outline, and get spotlighted in bundles.

```bash
uv run survey run anchors --topic my_topic
```

This writes `anchors_candidates_v1.csv` with columns: `bib_key`, `title`, `year`, `venue`, `venue_tier`, `llm_score` (0–5), `llm_reason`, `is_survey`, `suggested`, `your_decision`.

Fill the `your_decision` column (`yes` / `no`) and promote:

```bash
uv run survey topic curate-anchors --topic my_topic
```

This writes `anchors.csv`. Downstream rounds automatically pick it up.

---

### Round 3 — Extraction schema design

Reads each anchor paper's full text (`L0.md`) and proposes a JSON extraction schema tailored to your topic.

```bash
uv run survey run schema-design --topic my_topic
```

Writes `schemas/schema_v2.json` (or the next available version). Review and edit it manually, then promote:

```bash
uv run survey topic inspect-schema --topic my_topic --version v2
uv run survey topic promote-schema --topic my_topic --version v2
```

`inspect-schema` summarizes field coverage and flags invalid candidates, such as an empty `universal` schema or `_bundle_fields` that reference missing fields. Promotion refuses schemas that fail these guards. Successful promotion updates `schemas/current.txt`. The schema has two parts:

- **`universal`** — fields extracted for every paper: `problem`, `contributions`, `datasets`, `limitations`
- **`by_type`** — additional fields per paper type (e.g., `method_idea` and `main_results` for method papers)

Each `by_type` entry also has `_bundle_fields` listing which fields to surface in section bundles.

**Note:** A hand-written `schemas/schema_v1.json` and `schemas/current.txt` are required before running Round 4 if you skip Round 3. See `tests/fixtures/mini_topic/schemas/` for the format.

---

### Round 4 — Deep extraction and summaries

Reads each paper's full `L0.md` and extracts structured fields according to the current schema:

- `papers/<bib_key>/L1.json` — structured fields
- `papers/<bib_key>/L2.md` — 100–400-word narrative summary

Requires `meta.json` (Round 1) and `L0.md` (Round 0) for each paper.

```bash
uv run survey run round4 --topic my_topic
uv run survey run extract --topic my_topic --bib-key brown2020gpt3
uv run survey run round4 --topic my_topic --limit 3 --force
uv run survey run round4 --topic my_topic --workers 4    # parallel
```

**Cost:** capable model, ~$0.10–$0.30 per paper. This is the main API cost in the pipeline. Run `--limit 3` first.

**Schema upgrades:** if you promote a new schema later, re-extract only affected papers:

```bash
uv run survey run round4 --topic my_topic --force
```

---

### Round 5 — Outline proposal

Proposes 2–3 candidate outline structures based on every paper's L3 card and metadata. Anchor papers are tagged and weighted.

```bash
uv run survey run round5 --topic my_topic
```

Writes `outline_candidates_v1.md`. Each candidate contains a chapter tree (H2/H3 headings), estimated paper counts per section, and a trade-off paragraph.

**Human gate:** pick one candidate, edit section names and ordering as needed, and save as `outline.md` in the topic directory. This file is never overwritten by the system.

Before Round 6, check that `outline.md` contains only the final outline, not the full candidate proposal:

```bash
uv run survey topic inspect-outline --topic my_topic
```

---

### Round 6 — Section assignment and bundle generation

Assigns each paper to a section, then assembles one writing-ready markdown file per section.

```bash
uv run survey run round6 --topic my_topic
uv run survey run assign-section --topic my_topic --workers 4
uv run survey run build-bundles --topic my_topic --force
```

Writes:

- `section_assignments_v1.csv` — `bib_key`, `primary_section`, `secondary_sections`, `confidence`, `reason`
- `bundles/section_01_slug.md`, `bundles/section_02_slug.md`, … — one file per section

Each bundle contains: section description from the outline → anchor papers in that section (full L2 + key L1 fields) → other papers (L2 + compact L1) → cross-references (papers with a secondary assignment here).

**Human gate:** check low-confidence rows in `section_assignments_v1.csv`. Adjust `outline.md` or patch assignments manually if sections are unbalanced.

---

### Round 7 — Section drafting

Paste a bundle file into Claude (or any LLM chat). Ask it to draft that section. This is intentionally not scripted — the writing step benefits from interactive back-and-forth.

---

## Checking status

```bash
uv run survey topic status --topic my_topic
uv run survey topic status --topic my_topic --detailed   # shows review queue
```

The review queue (`_review_needed.csv`) accumulates items from all rounds: failed PDF parses, low-confidence triage, schema validation errors, low-confidence section assignments. Inspect it regularly.

---

## Re-running and loop-backs

Every op is idempotent. Existing artifacts are skipped unless `--force` is passed. Common loop-back scenarios:

- **New papers added** → run Round 0 → 1 → 4 → 6 for the new papers only (schema and outline stay unchanged unless the new batch introduces new dimensions)
- **Schema feels inadequate** → re-run Round 3 → promote → re-run Round 4 with `--force` → re-run Round 6
- **Outline restructured** → re-run Round 6

---

## Run logs

Every `survey run` command appends a JSONL record to `_runs/` with start/end time, processed/skipped/failed counts, and artifact paths:

```bash
ls my_topic/_runs/
```
