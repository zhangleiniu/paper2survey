# Survey System

Python 3.11+ skeleton for a file-backed survey writing system.

Install locally:

```bash
pip install -e .
```

Install with Marker PDF support:

```bash
pip install -e ".[marker]"
```

## Phase 1: Data Contracts and IO

Phase 1 loads topic state from `papers.csv` and `references.bib`, filters included
papers with `include == yes`, and reads or writes paper artifacts under
`papers/<bib_key>/`.

Implemented IO helpers:

- `survey_system.io.papers`: `iter_included`, `get_paper`, `set_include`
- `survey_system.io.bib`: `get_bib_entry`
- `survey_system.io.kb`: `read_meta`, `write_meta`, `read_L0`, `write_L1`

Contracts now include `Meta`, `L1Universal`, loose `L1ByType`, and `L2`.

Validate a topic fixture:

```bash
survey topic validate --topic tests/fixtures/mini_topic
```

The validator checks that `papers.csv` and `references.bib` have matching row
counts and keys, and that every listed PDF exists under `pdfs/`.

## Phase 2: Round 0 PDF Parsing

Round 0 converts included papers from `pdfs/<pdf_filename>` into
`papers/<bib_key>/L0.md` with Marker. Extracted images are written under
`papers/<bib_key>/_images/`.

Marker is optional because it downloads and loads large local models. A normal
development install can run IO tests without it:

```bash
pip install -e .
```

Install Marker support when you are ready to parse PDFs:

```bash
pip install -e ".[marker]"
```

Marker may require several GB of VRAM, depending on model configuration and PDF
content. The backend lazy-loads models on the first conversion and reuses the
same backend instance across the run.

Parse all included papers:

```bash
survey run round0 --topic tests/fixtures/mini_topic
```

Useful development variants:

```bash
survey run parse-pdf --topic tests/fixtures/mini_topic --bib-key smith2024widgets
survey run round0 --topic tests/fixtures/mini_topic --limit 1
survey run round0 --topic tests/fixtures/mini_topic --force
```

Existing non-empty `L0.md` files are skipped unless `--force` is passed. Missing
PDFs, repeated Marker failures, and very short L0 outputs are recorded in
`_review_needed.csv`.

The model-backed Marker fixture test is opt-in to keep normal test runs light:

```bash
RUN_MARKER_LIVE=1 pytest tests/test_pdf_marker_backend.py
```

## Phase 3: Round 1 Triage and L3 Cards

Round 1 uses the configured cheap LLM model to classify each included paper and
write:

- `papers/<bib_key>/meta.json`
- `papers/<bib_key>/L3.txt`

Run triage only:

```bash
survey run triage --topic tests/fixtures/mini_topic
survey run triage --topic tests/fixtures/mini_topic --bib-key smith2024widgets
survey run triage --topic tests/fixtures/mini_topic --limit 1 --force
```

Run the full Round 1 sequence:

```bash
survey run round1 --topic tests/fixtures/mini_topic
```

Round 1 reads only a short L0 excerpt: the abstract and first introduction
paragraph when markdown headings are available, or the first 2000 characters as
a fallback. Existing `meta.json` and `L3.txt` files are skipped unless `--force`
is passed.

The live LLM smoke test is opt-in:

```bash
RUN_LLM_LIVE=1 ANTHROPIC_API_KEY=... pytest tests/test_llm_client.py -m live
```

## Phase 4: Round 4 L1 Extraction and L2 Summaries

Round 4 uses the current manual schema in `schemas/current.txt` and
`schemas/schema_v1.json` to generate:

- `papers/<bib_key>/L1.json`
- `papers/<bib_key>/L2.md`

Automatic schema design is still deferred; for now, edit or replace the schema
files by hand before running extraction.

Run extraction only:

```bash
survey run extract --topic tests/fixtures/mini_topic --bib-key smith2024widgets
survey run extract --topic tests/fixtures/mini_topic --limit 3 --force
```

Run L2 summarization only:

```bash
survey run summarize-l2 --topic tests/fixtures/mini_topic --bib-key smith2024widgets
```

Run the full Round 4 sequence:

```bash
survey run round4 --topic tests/fixtures/mini_topic --limit 3
```

Extraction requires `meta.json` from Round 1 and `L0.md` from Round 0. Each
`L1.json` gets a top-level `_schema_version` so future schema upgrades can detect
stale extractions. L2 summaries are intended to be 100 to 400 words; outputs
outside that soft bound are written and flagged in `_review_needed.csv`.

## Phase 5: Outline, Assignment, and Bundles

Phase 5 is the MVP writing-bundle path:

1. Propose human-editable outline candidates.
2. Save the chosen candidate as `outline.md`.
3. Assign papers to outline sections.
4. Build section bundles under `bundles/`.

Propose outlines:

```bash
survey run round5 --topic tests/fixtures/mini_topic
survey run propose-outline --topic tests/fixtures/mini_topic --force
```

After editing or saving `outline.md`, run assignment and bundling:

```bash
survey run round6 --topic tests/fixtures/mini_topic
survey run assign-section --topic tests/fixtures/mini_topic --bib-key smith2024widgets
survey run build-bundles --topic tests/fixtures/mini_topic --force
```

If `anchors.csv` exists, outline prompts tag those papers with `(ANCHOR)`, and
bundles list anchor papers before other papers. Bundle entries include the
paper's `bib_key`, full L2 narrative, and selected key L1 fields from the
current schema's `_bundle_fields`.

## Phase 6: Anchor Recommendation

Round 2 recommends anchor papers for human review. It reads each included
paper's `L3.txt`, `meta.json`, venue, year, and configured venue tier, then
writes `anchors_candidates_v1.csv`.

Generate candidates:

```bash
survey run anchors --topic tests/fixtures/mini_topic
```

Review the CSV and set `your_decision` to `yes` for selected anchors, then
promote them:

```bash
survey topic curate-anchors --topic tests/fixtures/mini_topic
```

This writes `anchors.csv` with `bib_key` and `role_notes`. Later outline prompts
tag those papers with `(ANCHOR)`, and bundles put anchor papers before other
papers in each section.

## Phase 7: Automatic Schema Design

Round 3 generates a candidate extraction schema from anchor papers. It reads
`anchors.csv`, loads each anchor's `L0.md`, compares against the current schema,
and writes the next candidate file, such as `schemas/schema_v2.json`.

Generate a candidate schema:

```bash
survey run schema-design --topic tests/fixtures/mini_topic
```

After human review and edits, promote the selected schema:

```bash
survey topic promote-schema --topic tests/fixtures/mini_topic --version v2
```

Promotion updates `schemas/current.txt` and stamps the promoted schema's
`_provenance.promoted_at`. Re-extraction remains explicit:

```bash
survey run round4 --topic tests/fixtures/mini_topic --force
```
