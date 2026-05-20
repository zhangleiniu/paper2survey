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
