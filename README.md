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
