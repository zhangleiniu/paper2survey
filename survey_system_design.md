# Survey Writing System: Architecture Design

> This is an **architecture document**, not an implementation document. It defines the system's core abstractions, data contracts, operation set, default execution protocol, and file layout. Concrete code choices (language/library selection, exact prompt template text) are left for the implementation phase.
>
> **Audience:** (1) the project author, to clarify thinking and make design decisions; (2) a programming agent (Claude Code, Codex, etc.) that implements the scripts from this document.

---

## 1. Motivation

The hard part of writing a survey isn't collecting papers, and it isn't even reading them — it's the iterative process of **gradually building up an understanding of the topic**:

- You only know what fields to extract after reading some papers
- You only know how to categorize after extracting fields
- You only know how to organize chapters after categorizing
- You only know how to write after the chapter structure is settled

This is essentially **iterative discovery**. The system's job is to manage the intermediate artifacts of this process, so that each round's findings feed the next, and so that at every step the LLM sees an input that is "just enough" — not so little that the answer is vague, not so much that it eats the context window.

### 1.1 The one hard constraint: LLM context size

If LLM context were unlimited, this system would not need to exist — you could dump 100 full-text papers into the prompt and ask for a survey in one shot. All engineering complexity here comes from this single constraint.

The core strategy: **maintain multiple granularities of representation for each paper**, and on every LLM call **explicitly declare which granularity and which subset is being read**. Any operation that "reads every paper's full text" is illegal.

### 1.2 Goals

- Support topics of 30–300 papers
- Each round runs independently, idempotently, and is resume-safe
- Intermediate artifacts are versioned per round; loop-back never destroys history
- AI proposes, human decides — each round has an explicit human gate
- LLM-provider agnostic (any provider that supports structured output works)

### 1.3 Non-goals

- Fully automated writing
- Citation graph / external citation databases (listed as future extension)
- Multi-user collaboration
- Word-by-word drafting of the final prose (that happens in a chat interface; this system's job is to prepare the bundle that goes into chat)

### 1.4 Architectural constraints (library-first, UI-ready)

A GUI or web frontend may be added later (for editing `papers.csv`, working through the review queue, comparing outline candidates, viewing bundles). The current version is command-line, but the architecture **leaves room for UI**:

- **Every op is a library function** with the signature `op(topic_path, **args) -> result`. No embedded CLI logic, no `input()` calls, no interactive prompts. The CLI is a thin shell over the ops.
- **All state lives in files.** No hidden in-process state. Any frontend (CLI, UI, a text editor) opens the topic directory and reads the same files.
- **Status is queryable.** A `topic_status(topic_path) -> dict` function returns: which round you're in, the suggested next op, how many items are in the review queue, last-run timestamps for each op, etc. CLI and UI share this.
- **Declarative config.** `config.yaml` is the single source of op parameters; neither CLI nor UI introduces a separate configuration surface.
- **Long ops can run async.** Ops execute in the background and write logs to `_runs/{op}_{timestamp}.log`; the frontend polls the log. CLI defaults to foreground, UI to background.

These constraints demote "UI" from a feature to a frontend option — a web/desktop frontend can be added at any time as long as it reads/writes the same files and calls the same op functions.

### 1.5 Pipeline philosophy after topic-scale use

The system is a **structured writing-preparation pipeline**, not an autonomous survey author. Its strongest invariant is that every major step leaves a human-readable or inspectable artifact behind. The intended use is:

1. Compress the corpus into progressively smaller representations.
2. Insert human gates at irreversible decisions.
3. Use inspection commands to distinguish "file exists" from "artifact is complete and safe to trust."
4. Draft final prose manually from section bundles.

In practice, the highest-risk artifacts are not L0/L1/L2 themselves, but the **aggregate control artifacts**:

- `anchors.csv` can be empty if no candidate row was marked `your_decision = yes`.
- `schema_vN.json` can be syntactically present but semantically weak.
- `outline.md` can accidentally contain multiple candidate outlines.
- `bundles/` can contain stale files after an outline change.
- `_review_needed.csv` is append-only history, not current truth.

Therefore, quality inspection is a first-class design concern, not a polish feature.

---

## 2. Core Abstractions

### 2.1 Paper granularity levels

Each paper has up to four representations in the system:

| Level | Content | Size | Source |
|---|---|---|---|
| L0 | Full-text markdown | ~10–30k tokens | Marker (PDF → markdown), see §3.1 `parse_pdf` |
| L1 | Structured fields (JSON) | a few hundred tokens | LLM, extracted from L0 |
| L2 | Narrative summary | 100–300 tokens | LLM, compressed from L1 (+ L0 if needed) |
| L3 | One-sentence card | ~30 tokens | LLM, compressed from L2 |

Plus paper-level metadata. **Metadata has two sources:**

- **Human-provided (authoritative):** `bib_key, title, year, venue, pdf_filename, include, exclusion_reason, user_notes` come from `papers.csv`; the full BibTeX entry comes from `references.bib`. The system never modifies these fields.
- **System-derived:** `paper_type, paper_type_confidence, tldr, topics, anchor` are produced by triage and downstream ops, stored in `meta.json`.

**Important: year, venue, authors, and other metadata are always supplied by the human-curated CSV / BibTeX, never extracted from L0.** This information is often missing or unreliable in full PDFs (preprint vs. camera-ready differences, missing headers, garbled author lists). Forcing the LLM to recover it is a bad trade. The human CSV is the single source of truth; any downstream op needing metadata queries the CSV.

**L1 is the most important abstraction in the system.** It is structured (queryable, comparable across papers), but small enough that "the L1 of dozens of papers" fits in one prompt. L2 retains the narrative texture that L1 loses, used for section bundles during drafting. L3 is built for "whole-corpus reasoning" and must stay strictly bounded in context.

### 2.2 Corpus-level aggregates

Each topic also has a set of corpus-level artifacts, **versioned per round** (`outline_v1.md`, `outline_v2.md`, ...), so loop-back never overwrites history:

- `vocabulary` — terms, method names, datasets, and metrics that recur across the corpus
- `schema` — the current per-topic field definitions used for L1 (in JSON Schema format)
- `anchors` — the human-confirmed list of key papers
- `outline` — the selected chapter structure
- `section_assignments` — paper → section mapping
- `bundles/` — one writing-input file per section

Aggregates are produced by "cross-paper ops" and consumed by "per-paper ops or writing ops".

### 2.3 Granularity-scope matrix (hard rule)

> **No op may "read every paper at the finest granularity."**

Specifically:

| Op scope | Granularity used | Approximate token budget |
|---|---|---|
| Whole corpus (hundreds of papers) | L3 + meta | ~5k |
| Whole corpus, needs structured comparison | Selected L1 fields | ~10–20k |
| Anchor set (5–15 papers) | L0 | ~50–150k |
| Single section (10–25 papers) | L2 + selected L1 | ~5–15k |
| Single paper (deep read) | L0 | ~10–30k |

This table is the engineering contract that lets the system scale. Every op's spec must fit on one of these rows.

### 2.4 Human-gate inspection surfaces

Every human gate should have a small, explicit inspection surface:

| Decision | Primary artifact | Inspection command | Failure caught |
|---|---|---|---|
| Topic setup | `papers.csv`, `references.bib`, `pdfs/` | `survey topic validate` | missing PDFs, BibTeX mismatch |
| Schema promotion | `schemas/schema_vN.json` | `survey topic inspect-schema` | empty universal fields, broken bundle fields |
| Outline finalization | `outline.md` | `survey topic inspect-outline` | full candidate proposal copied as final outline |
| Assignment review | `section_assignments_v1.csv` | `survey topic inspect-assignments` | missing papers, overload, low confidence |
| Whole pipeline status | topic directory | `survey topic status --detailed` | incomplete coverage, stale bundles, stale review items |
| Per-paper pipeline state | `_status/papers.csv` | `survey topic paper-status` | which paper failed or still needs review |
| Per-paper content matrix | `_analysis/paper_matrix.csv` | `survey topic paper-matrix` | cross-paper comparison by schema fields |

Inspection commands must not mutate state. They are deliberately separate from the ops that generate artifacts.

---

## 3. Operations

Each op is a `read(KB) → write(KB)` function. **Per-paper ops handle single-paper I/O** (batching is the driver script's job); **aggregate ops take a corpus subset as input.** All ops are idempotent: same input produces same output (modulo LLM non-determinism).

Each op declares: input, output, model tier (cheap / capable), context budget, and failure modes.

**Global filter convention:** when iterating over the corpus, every op **only considers papers where `papers.csv:include == yes`.** Papers marked `include == no` are excluded from all downstream analysis — they don't appear in bundles, don't affect the outline, don't show up in anchor recommendations — even if their L0/L1/L2/L3 artifacts already exist. **Exclusion is a purely manual action** (edit the `include` column in `papers.csv`); no new op is needed. It can be done at any round. Artifacts of excluded papers are not deleted, in case you change your mind and re-include them later.

### 3.1 Per-paper operations

#### `parse_pdf(pdf_path) → L0`

Convert a PDF into markdown. **This is the first step of the pipeline** — without L0, no downstream op can run.

- **Input:** `pdfs/{pdf_filename}` (a PDF file referenced from `papers.csv:pdf_filename`)
- **Output:** `papers/{bib_key}/L0.md` (full-text markdown), and optionally `papers/{bib_key}/_images/` for any figures Marker extracts
- **Implementation:** uses [Marker](https://github.com/datalab-to/marker) (`marker-pdf` on PyPI) by default. Marker preserves headings, tables, equations, and reading order better than naive extractors. A fast PyMuPDF backend is available for text-only digital PDFs.
- **Model tier:** N/A for the LLM client (Marker runs its own local vision models — ~3–5 GB VRAM, or CPU if no GPU is available)
- **Context budget:** N/A (the LLM is not called here)
- **Failure modes:**
  - PDF is a pure scan with no embedded text → Marker auto-detects this via its built-in OCR (surya), but quality varies. If the extracted L0 is shorter than a configurable minimum (e.g., 1000 chars) → flag in `_review_needed.csv`.
  - PDF is corrupt / password-protected → write a row to `_review_needed.csv` and skip; no L0 is created.
  - Marker encounters an internal error → retry once, then flag for review.
- **Idempotency:** if `L0.md` exists and is non-empty, skip unless `--force`. Marker is the most expensive non-LLM step in the pipeline (seconds-to-minutes per paper depending on hardware), so cheap re-runs matter.
- **Configuration knobs** exposed via `config.yaml`:
  - `force_ocr` (bool) — force OCR even on digital PDFs; useful for older scanned papers
  - `use_llm` (bool) — Marker's optional LLM-assisted mode that improves table/equation accuracy at extra cost
  - `torch_device` (`auto` / `cpu` / `cuda` / `mps`) — `auto` resolves to a real PyTorch device before calling Marker
  - `save_images` (bool) — write extracted images only when needed; downstream text-only pipeline does not consume them
  - `backend` (`marker` / `pymupdf`) — choose richer local ML parsing or fast text extraction
- **Note on metadata:** Marker also emits a metadata JSON (title, page count, etc.). The system **ignores it** — `papers.csv` is the authoritative metadata source (see §2.1).

#### `triage(L0_excerpt) → meta`

- **Input:** the abstract and first paragraph of the introduction from L0 (excerpted; full text is not read)
- **Output:** `papers/{bib_key}/meta.json`, containing only system-derived fields: `paper_type, paper_type_confidence, tldr, topics[]`
- **Model tier:** cheap
- **Context budget:** ~2k
- **Failure modes:** confidence below threshold → write to `_review_needed.csv`
- **`paper_type` enumeration:** `survey, method, benchmark, dataset, analysis, position, application, tool_system`
- **Does not extract:** year, venue, author, or any other field already provided by the human CSV. Triage's job is **classification + summarization**, not metadata reconstruction.

#### `extract_L1(L0, schema, paper_type) → L1`

- **Input:** full L0 + current schema + paper_type
- **Output:** `papers/{bib_key}/L1.json`, conforming to the `paper_type` sub-schema in `schema_v{n}.json`
- **Model tier:** capable (needs reliable structured output)
- **Context budget:** ~10–30k (depends on paper length)
- **Failure modes:** schema validation fails → retry once with the error message; second failure → flag for review
- Every L1 file carries a `_schema_version` field, so future re-extraction can target only affected papers.

#### `summarize_L2(L1, L0) → L2`

- **Input:** L1 primarily, with optional look-back to L0 for narrative detail
- **Output:** `papers/{bib_key}/L2.md`, a 100–300-word narrative paragraph
- **Model tier:** cheap
- **Context budget:** ~5k

#### `summarize_L3(L2) → L3`

- **Input:** L2 only
- **Output:** `papers/{bib_key}/L3.txt`, a single 15–35-word sentence
- **Model tier:** cheap
- **Context budget:** ~1k

#### `assign_section(L2, outline) → assignment_row`

- **Input:** a single paper's L2 + the full `outline.md`
- **Output:** one row appended to `section_assignments_v{n}.csv`: `bib_key, primary_section, secondary_sections, confidence, reason`
- **Model tier:** cheap
- **Context budget:** ~3k
- **Failure modes:** low confidence → review queue
- **Convention:** multi-label assignments are allowed, but only `primary_section` decides which bundle the paper goes into; secondary assignments only generate cross-references in the outline.

### 3.2 Aggregate operations

#### `propose_anchors(L3_of_all + meta + venue_tier_map) → anchors_candidates`

- **Input:** every paper's L3 + meta (including venue from CSV) + the `venue_tier` mapping from topic config
- **Output:** `anchors_candidates_v{n}.csv`, with columns: `bib_key, title, year, venue, venue_tier, llm_score (0-5), llm_reason, is_survey, suggested (bool), your_decision (empty)`
- **Model tier:** capable (scoring needs to be stable)
- **Context budget:** ~5k
- **Algorithm:**
  1. The script computes `venue_tier` (by string match against config) and `is_survey` (from meta)
  2. The LLM gives each paper an `llm_score` and one-sentence `llm_reason` based on L3 + meta
  3. The script fills `suggested` by rule: `is_survey == true` OR `(venue_tier == 1 AND llm_score >= 4)`
- **Human gate:** the human fills the `your_decision` column (yes/no); the curated result is saved as `anchors.csv`

#### `design_schema(L0_of_anchors, prior_schema?) → schema_v{n+1}`

- **Input:** the full L0 of the anchor papers (5–15 papers) + the previous schema if any
- **Output:** `schemas/schema_v{n+1}.json`
- **Model tier:** capable
- **Context budget:** ~100k
- **Process:**
  1. For each anchor, ask the LLM to extract "the dimensions this paper uses to compare other methods" and "any explicit taxonomy proposals."
  2. Aggregate: any dimension mentioned by ≥3 anchors goes into the schema; conflicting dimensions are listed for review.
  3. Split by paper_type into sub-schemas (universal + by_type).
- **Human gate:** run schema inspection, review the candidate schema, edit manually if needed, mark as current.
- **Quality guardrails:** promotion must reject candidates with an empty or malformed `universal` object, missing paper types, invalid `required` references, or `_bundle_fields` that point to fields not present in the type schema.
- **Design note:** schema design is a draft generator. It should preserve useful prior fields unless the human explicitly accepts a breaking change.

#### `build_vocabulary(L1_of_all) → vocabulary_v{n}`

- **Input:** all L1 files
- **Output:** `vocabulary_v{n}.json`, frequency-sorted lists of methods / datasets / metrics / concepts
- **Model tier:** no LLM, or only used for variant merging
- **Context budget:** N/A (mostly script logic)

#### `propose_outline(L3_of_all + meta + anchor_flags) → outline_candidates`

- **Input:** every paper's L3 + meta + anchor flags
- **Output:** `outline_candidates_v{n}.md`
- **Model tier:** capable
- **Context budget:** ~10k
- **The LLM is asked to produce** 2–3 candidate outlines. For each:
  - The main organizing axis (method paradigm / problem subtype / learning paradigm / etc.)
  - A tree structure (chapter → section)
  - The estimated paper count per section (so you can see bucket balance)
  - A short trade-off analysis
- **Anchor weighting:** anchor papers' L3s are explicitly tagged in the prompt, and the LLM is told that the outline must cover them well.
- **Human gate:** pick one candidate, edit section names / order / merges, save as `outline.md`, then inspect it. `outline.md` must contain one final H2/H3 tree, not the full candidate proposal.

#### `build_bundles(L1+L2 of all, section_assignments, anchors) → bundles/`

- **Input:** all L1 + L2 + current assignments + anchors
- **Output:** one `bundles/section_{N}_{slug}.md` per section
- **Model tier:** no LLM (pure script assembly)
- **Bundle structure:**
  - The section title + description copied from outline
  - **Anchor papers in this section** (if any): full L2 + selected L1 fields per paper
  - **Other papers in this section**: L2 + compact L1 per paper
  - **Cross-references** (if any): papers whose `secondary_section` hits this section — title + bib_key only
  - Every entry carries its `bib_key` for `\cite{}` use
- **Ordering:** anchors first, then by year or sub-cluster
- **Stale handling:** forced rebuilds remove bundle markdown files that do not correspond to the current parsed outline.

---

## 4. Default Protocol

There are 8 default rounds (Round 0 through Round 7). Any round can be redone; downstream rounds may need to be partially re-run on the affected subset.

```
Round 0  PDF ingestion        → every included paper has L0.md
Round 1  Reconnaissance       → corpus shape is known
Round 2  Anchor selection     → focus on key papers
Round 3  Schema design        → define "which fields are worth extracting"
Round 4  Deep extraction      → all papers structured
Round 5  Outline proposal     → chapter structure
Round 6  Assign + bundle      → writing inputs are ready
Round 7  Section drafting     → actual writing (in chat)
```

### Round 0 — PDF ingestion

- **Input:** PDFs in `pdfs/`; `papers.csv` rows whose `include == yes` (the `pdf_filename` column maps a row to its PDF)
- **Ops:** `parse_pdf` (per paper)
- **Output:** `papers/{bib_key}/L0.md` for every included paper; rows for any paper with extraction problems written to `_review_needed.csv`
- **Human gate:**
  1. Skim a few L0.md files to confirm headings / tables / equations look reasonable
  2. For papers flagged in `_review_needed.csv`: either fix manually (re-run with `--force_ocr`, replace with a better PDF, etc.) or mark `include = no` in `papers.csv` if the paper is unsalvageable
- **Purpose:** convert PDFs to a form every downstream op can consume. This is the only round that uses local ML models (Marker's surya / layout models). The rest of the pipeline only needs an LLM API and disk.
- **Cost note:** Marker runs locally (no API cost), but it's the slowest step in the pipeline. On CPU, ~30–120 seconds per paper; on a GPU, ~5–15 seconds. For a 100-paper corpus, budget several minutes to a few hours of wall time for this round.

### Round 1 — Reconnaissance

- **Input:** `papers.csv` (human-curated); `papers/{bib_key}/L0.md` (from Round 0)
- **Ops:** `triage` → `summarize_L3` (Round 1 can use the triage `tldr` as a starting point for L3)
- **Output:** `meta.json` and `L3.txt` per paper; `R1_distribution.csv` summarizing the paper_type distribution
- **Human gate:**
  1. Sanity-check the paper_type distribution
  2. Spot-check 5 low-confidence cases
  3. **Based on the tldrs, mark obviously irrelevant papers as `include = no`** (Round 1 is the most natural first moment for exclusion)
- **Purpose:** know what kinds of paper are in this corpus, overall size, how many are surveys; first-pass filtering of irrelevant items.

### Round 2 — Anchor selection

- **Input:** all L3 + meta; `config.yaml`'s `venue_tier` map
- **Ops:** `propose_anchors`
- **Output:** `anchors_candidates_v1.csv`
- **Human gate:** fill `your_decision`, save curated result as `anchors.csv`
- **Purpose:** select 5–15 anchor papers. They serve three purposes:
  1. Your own priority reading list (to build intuition)
  2. Input to Round 3's schema design
  3. Weighting signal in Round 5's outline proposal; spotlights in Round 7's writing

### Round 3 — Schema design

- **Input:** the L0 of anchor papers (from `anchors.csv`)
- **Ops:** `design_schema`
- **Output:** `schemas/schema_v1.json`
- **Human gate:** inspect, review, edit manually, mark current
- **Purpose:** define "for this topic, what structured fields are worth extracting from every paper."

### Round 4 — Deep extraction

- **Input:** each paper's L0 + the current schema + that paper's paper_type
- **Ops:** `extract_L1` (per paper, parallelizable) → `summarize_L2`
- **Output:** `L1.json` and `L2.md` per paper; problematic papers accumulated in `_review_needed.csv`
- **Human gate:** process the review queue
- **Purpose:** every paper enters a "ready for structured comparison" state.
- **Cost estimate:** 100 papers × one capable-model call ≈ the bulk of the pipeline's API spend, concentrated in this round.

### Round 5 — Outline proposal

- **Input:** all L3 + meta + anchor flags; optionally `vocabulary_v1`
- **Ops:** optionally `build_vocabulary` first → `propose_outline`
- **Output:** `outline_candidates_v1.md`, with 2–3 candidates
- **Human gate:** pick one, edit, save as `outline.md`
- **Purpose:** the topic's chapter structure is settled.

### Round 6 — Assignment + bundling

- **Input:** each paper's L2, `outline.md`, `anchors.csv`
- **Ops:** `assign_section` (per paper) → `build_bundles`
- **Output:** `section_assignments_v1.csv`, `bundles/section_*.md`
- **Human gate:** inspect assignment quality, scan low-confidence rows, adjust the outline or hand-patch assignments
- **Purpose:** one writing-ready context file per section.

### Round 7 — Section drafting

- **Input:** a single bundle, full `outline.md`, sections already drafted
- **Ops:** `draft_section` — **performed manually in a chat interface; this is not a script in the system**
- **Output:** prose draft per section (`drafts/section_*.md`)
- **Human gate:** writing is the gate
- **Purpose:** the survey draft.

The system stops at writing bundles intentionally. A bundle is a context package for one section, not finished prose. The recommended drafting loop is: choose one bundle, ask a chat model to synthesize across papers with citations, manually edit, then cross-check against L1 fields and BibTeX keys.

### Loop-back triggers

- Round 5 suspects the L1 fields don't differentiate papers enough → back to Round 3 to upgrade the schema → Round 4 re-extracts affected papers → back to Round 5
- Round 6 has too many outliers → back to Round 5 to change the outline
- Round 7 reveals mid-draft that a section needs to be split → back to Round 5/6 for the affected subtree
- New papers added → for the new papers only, run Round 0 → 1 → 4 → 6 (anchors / schema / outline are not changed unless the new batch introduces new dimensions)

### Current quality reports

The mature pipeline should expose these non-mutating reports:

- `topic status --detailed`: coverage of each round, active vs. stale review items, assignment coverage, bundle staleness
- `topic inspect-schema`: field coverage, validation issues, warnings about removed universal fields
- `topic inspect-outline`: parsed sections and candidate-output leftovers
- `topic inspect-assignments`: section counts, empty sections, overloaded sections, low confidence rows

These reports are part of the correctness model. A generated file is not enough to declare a round complete; the report must show adequate coverage and no blocking issues.

---

## 5. Data Contracts

### `papers.csv` (human-curated, input)

| Column | Description |
|---|---|
| `bib_key` | Primary key, matching an entry key in `references.bib`, used in LaTeX `\cite{}` |
| `title` | |
| `year` | Human-filled, never PDF-extracted |
| `venue` | String, must match the `venue_tier` map in config |
| `pdf_filename` | Filename (with extension), located under `topics/<topic_name>/pdfs/`. Free-form, keep it human-readable (this is the name you see when you open the PDF) |
| `include` | `yes` / `no`, defaults to `yes`. Every downstream op only processes `yes` rows |
| `exclusion_reason` | Filled when `include == no`, free text. **Note:** a survey paper may want a "directions we considered and excluded" paragraph; this column is its source material |
| `notes` | Optional, free-text human notes |

### `references.bib` (human-maintained, input)

A standard BibTeX file where each entry's key matches a `bib_key` in `papers.csv` exactly. Claude's output of `\cite{bib_key}` during writing maps directly to entries here.

The system **does not modify** this file. Ops like `build_bundles` may **optionally** consult it for full author lists or expanded venue names, but no op depends on it (every op can complete using only `papers.csv` columns).

> **Why separate from `papers.csv`:** BibTeX entries are multi-line (author lists, URLs, abstracts) and don't fit in CSV columns. Separately, BibTeX is the native format of the LaTeX toolchain, so keeping it isolated makes the writing pipeline cleaner.

### `topics/<topic_name>/config.yaml`

```yaml
topic_name: gnn_vulnerability_detection

venue_tiers:
  tier_1: [NeurIPS, ICML, ICLR, S&P, USENIX Security, CCS, NDSS]
  tier_2: [AAAI, IJCAI, AISTATS, ESORICS]
  tier_3: [arXiv]

paper_types:
  - survey
  - method
  - benchmark
  - dataset
  - analysis
  - position
  - application
  - tool_system

models:
  triage: <cheap_model_id>
  extract: <capable_model_id>
  summarize: <cheap_model_id>
  schema_design: <capable_model_id>
  outline: <capable_model_id>
  assign: <cheap_model_id>

thresholds:
  triage_confidence_review_below: 0.7
  assign_confidence_review_below: 0.7
  extract_retry_on_validation_fail: 2
  parse_pdf_min_chars: 1000     # L0 shorter than this triggers review

marker:
  torch_device: auto            # auto | cpu | cuda | mps
  force_ocr: false              # true = OCR every page even on digital PDFs
  use_llm: false                # true = use Marker's optional LLM mode (extra cost)
```

### `papers/{bib_key}/meta.json`

Only system-derived fields (human fields stay in `papers.csv` / `references.bib`, never copied here):

```json
{
  "bib_key": "smith2023gnnvuln",
  "paper_type": "method",
  "paper_type_confidence": 0.95,
  "tldr": "Proposes a GNN architecture for detecting smart-contract reentrancy by analyzing control-flow graphs.",
  "topics": ["reentrancy", "smart_contracts", "gnn"],
  "anchor": false,
  "_generated_at": "2026-05-18T12:00:00Z"
}
```

`anchor` is written by Round 2. Downstream ops needing year/venue/title read `papers.csv` directly (join by `bib_key`), not meta.

### `papers/{bib_key}/L0.md`

The full-text markdown produced by Marker. Plain markdown, no front matter. Image references (if any) point to `_images/` siblings.

### `papers/{bib_key}/_images/` (optional)

Figures extracted by Marker, named according to Marker's output convention (e.g., `_page_3_Figure_1.png`). The system does not currently consume images, but they're kept for potential future use (figure references in bundles, OCR of complex diagrams, etc.).

### `papers/{bib_key}/L1.json`

```json
{
  "_schema_version": "v2",
  "_paper_type": "method",
  "universal": {
    "problem": "...",
    "prior_limitation": "...",
    "contributions": ["...", "..."],
    "datasets": ["..."],
    "limitations": ["..."]
  },
  "type_specific": {
    "method_idea": "...",
    "components": ["..."],
    "baselines": ["..."],
    "main_results": {"metric_name": "value"},
    "ablations": ["..."]
  },
  "_generated_at": "2026-05-18T12:00:00Z"
}
```

Each paper_type has its own `type_specific` sub-schema in `schema_v{n}.json`. The `universal` block is shared across all paper_types.

### `papers/{bib_key}/L2.md`

A 100–300-word narrative paragraph, plain markdown, no front matter.

### `papers/{bib_key}/L3.txt`

A single 15–35-word sentence, plain text.

### `schemas/schema_v{n}.json`

JSON Schema format:

```json
{
  "version": "v2",
  "universal": { /* JSON Schema for universal fields */ },
  "by_type": {
    "method": { /* JSON Schema */ },
    "survey": { /* ... */ },
    "benchmark": { /* ... */ },
    "...": {}
  },
  "_provenance": {
    "based_on_anchors": ["bib_key1", "bib_key2"],
    "promoted_at": "2026-05-18T...",
    "delta_from_prev": "Added 'attack_target' field for method papers"
  }
}
```

### `anchors_candidates_v{n}.csv`

| Column | Description |
|---|---|
| `bib_key` | |
| `title`, `year`, `venue` | So the human doesn't have to cross-reference tables while deciding |
| `venue_tier` | 1 / 2 / 3 |
| `llm_score` | 0–5 |
| `llm_reason` | One sentence |
| `is_survey` | bool |
| `suggested` | Boolean recommendation computed by script |
| `your_decision` | Empty, to be filled by the human (yes / no) |

### `anchors.csv` (human-curated)

| Column | Description |
|---|---|
| `bib_key` | |
| `role_notes` | Optional, describing why this paper is an anchor (used as material when writing spotlights) |

### `vocabulary_v{n}.json`

```json
{
  "methods": [{"term": "GNN", "count": 47, "papers": ["..."]}, ...],
  "datasets": [{"term": "SmartBugs", "count": 12, "papers": ["..."]}, ...],
  "metrics": [...],
  "concepts": [...]
}
```

### `outline_candidates_v{n}.md`

Three H1 sections (one per candidate), each containing:

- An H2 explaining the organizing axis
- The chapter tree, expressed as H3/H4 nesting
- After each leaf section, a paper-count estimate in parentheses, e.g. `(~12 papers)`
- An H2 "Trade-offs" paragraph
- An H2 "Spot-check" listing several anchor papers under this outline, confirming each lands in a sensible place

### `outline.md`

The final selection. Hierarchical markdown headers; each leaf section followed by a 1–2-sentence description.

### `section_assignments_v{n}.csv`

| Column | Description |
|---|---|
| `bib_key` | |
| `primary_section` | A leaf section path from the outline, e.g. `3.2 Dynamic Detection` |
| `secondary_sections` | Semicolon-separated section paths, may be empty |
| `confidence` | 0–1 |
| `reason` | One sentence |

### `bundles/section_{N}_{slug}.md`

```markdown
# Section {N}: {Title}

> {section description from outline}

## Anchor papers in this section

### {Title 1} ({year}, {venue}) [{bib_key1}]
{L2 of paper 1}

**Key fields (from L1):**
- problem: ...
- method_idea: ...
- datasets: ...
- main_results: ...

### {Title 2} (...)
...

## Other papers in this section

### {Title 3} ({year}, {venue}) [{bib_key3}]
{L2 of paper 3}

**method_idea**: ...; **datasets**: ...; **main_results**: ...

(compact L1 inline format)

...

## Cross-references

Papers with secondary assignment to this section:
- [{bib_key_x}] {Title} (primary: Section 4.1)
- ...
```

---

## 6. Storage Layout

```
topics/<topic_name>/
    papers.csv                          # Human-curated input
    references.bib                      # Human-maintained BibTeX
    config.yaml                         # Topic-level configuration

    pdfs/                               # User-placed PDF source files
        Smith2023-gnn-vulnerability.pdf # Human-readable filenames
        Jones2024-survey.pdf            # papers.csv:pdf_filename maps to bib_key
        ...

    papers/<bib_key>/                   # System-derived artifacts, keyed by bib_key
        L0.md                           # Marker output (Round 0)
        _images/                        # Figures extracted by Marker (optional)
        meta.json                       # triage output
        L1.json                         # extract output
        L2.md                           # summarize output
        L3.txt

    schemas/
        schema_v1.json
        schema_v2.json
        current.txt                     # Contents: current version string, e.g. "v2"

    vocabulary_v1.json
    vocabulary_v2.json

    anchors_candidates_v1.csv
    anchors_candidates_v2.csv
    anchors.csv                         # Human-curated (no version suffix)

    outline_candidates_v1.md
    outline_candidates_v2.md
    outline.md                          # Human-selected/edited (no version suffix)

    section_assignments_v1.csv
    section_assignments_v2.csv

    bundles/
        section_01_intro.md
        section_02_static.md
        ...

    drafts/                             # Writing output
        section_01.md
        ...

    _runs/                              # Op execution logs (UI can display status from here)
        parse_pdf_20260518T100000.log
        triage_20260518T120000.log
        extract_20260518T150000.log
        ...

    _status/
        papers.csv                      # Derived per-paper pipeline status

    _analysis/
        paper_matrix.csv                # Derived schema-backed content matrix

    _review_needed.csv                  # Cross-op human review queue
    R1_distribution.csv                 # Per-round summary statistics
    R2_anchor_stats.csv
    ...
```

### Naming conventions

- **Regeneratable artifacts** carry a `_v{n}` suffix (schema, outline_candidates, assignments, vocabulary, etc.)
- **Human-curated artifacts** have no version suffix (`papers.csv`, `anchors.csv`, `outline.md`, `drafts/`); these are authoritative and never overwritten by scripts
- **Current-version pointer for versioned artifacts:** use `current.txt` containing the version string, or a symlink
- **Topics are fully isolated:** all content lives under `topics/<topic_name>/`; topics share no state

### The work queue

`_review_needed.csv` is the cross-op human review queue. Any op that detects low confidence, schema validation failure, or extraction problems appends a row:

| Column | Description |
|---|---|
| `op_name` | Which op reported it |
| `bib_key` | Which paper (may be empty for aggregate ops) |
| `issue` | Short description |
| `details_path` | Relative path to the detailed log |
| `resolved` | Human fills `yes` after handling |

---

## 7. Open Questions & Future Extensions

### 7.1 Open questions

- **When to upgrade the schema?** Concrete scenario: in Round 3 you settle on `schema_v1` (15 fields); in Round 4 you extract L1.json for all 100 papers; in Round 5 you (or the LLM) realize "for dynamic-detection papers, 'instrumentation overhead' is a key distinguishing dimension, but `schema_v1` doesn't have it. Adding it would make the outline cleaner."
  
  Two options:
  
  - **A. Automatic upgrade:** the system detects low outline confidence or unbalanced buckets, auto-triggers `schema_v2`, and re-extracts affected papers' L1.
  - **B. Manual trigger:** the system surfaces a "schema may be inadequate" signal but you explicitly decide whether to upgrade. Upgrading triggers a Round 3 re-run (with "new field: instrumentation_overhead" as input) plus selective Round 4 re-extraction.
  
  **This document defaults to B.** Reason: auto-upgrade tends to make schemas bloat indefinitely; frequent schema changes lead to a mix of "papers extracted with v1" and "papers extracted with v2," breaking downstream cross-paper comparison. B treats schema evolution as deliberate versioned releases — each upgrade has a clear why, scope, and delta. The cost is one extra manual decision per upgrade.
- **`section_assignment` for survey papers:** papers with `paper_type == survey` usually don't belong to a single section — they inform the entire topic. Should `assign_section` skip them? **Current default: yes, skip.** Survey papers are introduced as secondary context for every section during writing.
- **`paper_type` changes:** if a re-run of triage reclassifies a paper's `paper_type`, its L1 may need to be re-extracted against the new sub-schema. The system **detects and flags this**; it does not auto-re-extract.

### 7.2 Future extensions

- **GUI / web frontend:** the library-first architecture (§1.4) means a UI is just another caller of the library, not a refactor. Suggested first cut: (a) a merged viewer for `papers.csv` + `meta.json` supporting rapid `include` toggling; (b) a side-by-side viewer for `outline_candidates` plus a "save as outline.md" action. Zero backend changes.
- **Citation graph:** extract references from L0 (LLM or GROBID), then fuzzy-match against in-corpus titles. Add `meta.cites_within_corpus[]` and `meta.cited_by_within_corpus[]` as extra signal for `propose_anchors`. No abstraction needs to change.
- **Cross-topic surveys:** a survey spanning multiple subtopics could be modeled as several topics sharing one final outline. The current per-topic isolation would need to be loosened.
- **Quality metrics:** track per-round L1 schema fill rate, triage confidence distribution, assignment confidence distribution. Surface to a `_health.md`.
- **Auto loop-back suggestions:** when outline-candidate confidence is low or buckets are very uneven, suggest going back to Round 3 to add fields. Currently fully manual.
- **L0 truncation / chunking:** very long papers (>50 pages) may produce L0 that exceeds even the capable model's context. Introduce a chunk-and-merge strategy without changing the L1 schema shape.
- **Alternative PDF parsers:** Marker is heavy (~5 GB VRAM, slow on CPU). For users without GPU access, a faster fallback (`pymupdf4llm`, `markitdown`) could be plugged into `parse_pdf` via a configuration flag. The op interface (`pdf_path → L0.md`) does not change.

---

## 8. Implementation priority

In the order of "unlock first, then enhance":

1. **PDF ingestion (Marker) + L0/L1/L2/L3 multi-granularity + `extract_L1` + `summarize_L2/L3`** — unlocks the multi-granularity context management at 50+ paper scale (the current core bottleneck). Without Round 0, nothing else runs; without L1, no structured comparison is possible.
2. **Triage + paper_type routing** — lets downstream ops branch on paper type.
3. **Outline + assign + bundle trio** — makes 50+ paper writing manageable.
4. **Anchor recommendation + schema design** — keeps the schema from being purely guesswork.
5. **Vocabulary, health metrics, auto loop-back suggestions** — quality-of-life.
6. **Citation graph, cross-topic** — long-term extensions.
