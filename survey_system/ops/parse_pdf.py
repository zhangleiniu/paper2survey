from __future__ import annotations

import csv
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable

from survey_system.config import load_config
from survey_system.io.contracts import FailureItem, OpResult, PaperRow
from survey_system.io.papers import get_paper, iter_included
from survey_system.paths import (
    paper_artifacts_dir,
    paper_images_dir,
    paper_l0_path,
    pdfs_dir,
    review_needed_csv,
    runs_dir,
)
from survey_system.pdf.marker_backend import MarkerBackend
from survey_system.pdf.pymupdf_backend import PyMuPDFBackend


def parse_pdf(
    topic_path: Path,
    bib_key: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    backend: MarkerBackend | None = None,
    progress_callback: Callable[[int, int, PaperRow, str], None] | None = None,
) -> OpResult:
    started = time.monotonic()
    config = load_config(topic_path)
    papers = _select_papers(topic_path, bib_key, limit)
    result = OpResult(op_name="parse_pdf")
    logger, log_path = _run_logger(topic_path)
    result.artifacts_written.append(log_path)

    if backend is None and papers:
        if config.marker.backend == "pymupdf":
            backend = PyMuPDFBackend()
        else:
            backend = MarkerBackend(
                torch_device=config.marker.torch_device,
                force_ocr=config.marker.force_ocr,
                use_llm=config.marker.use_llm,
                save_images=config.marker.save_images,
            )

    total = len(papers)
    for index, paper in enumerate(papers, start=1):
        l0_path = paper_l0_path(topic_path, paper.bib_key)
        if l0_path.exists() and l0_path.stat().st_size > 0 and not force:
            result.skipped.append(paper.bib_key)
            _log(logger, "skip_existing", paper.bib_key, str(l0_path))
            _report_progress(progress_callback, index, total, paper, "skipped")
            continue

        pdf_path = pdfs_dir(topic_path) / paper.pdf_filename
        if not pdf_path.exists():
            reason = f"missing PDF: {pdf_path}"
            _flag_review(topic_path, paper.bib_key, "parse_pdf", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            _log(logger, "missing_pdf", paper.bib_key, str(pdf_path))
            _report_progress(progress_callback, index, total, paper, "failed")
            continue

        if dry_run:
            result.skipped.append(paper.bib_key)
            _log(logger, "dry_run", paper.bib_key, str(pdf_path))
            _report_progress(progress_callback, index, total, paper, "skipped")
            continue

        assert backend is not None
        try:
            parsed = _convert_with_retry(backend, pdf_path)
        except Exception as exc:
            reason = f"PDF parsing failed after retry: {exc}"
            _flag_review(topic_path, paper.bib_key, "parse_pdf", reason)
            result.failed.append(FailureItem(bib_key=paper.bib_key, reason=reason))
            _log(logger, "pdf_parse_failed", paper.bib_key, reason)
            _report_progress(progress_callback, index, total, paper, "failed")
            continue

        paper_artifacts_dir(topic_path, paper.bib_key).mkdir(parents=True, exist_ok=True)
        l0_path.write_text(parsed.markdown, encoding="utf-8")
        result.artifacts_written.append(l0_path)

        if config.marker.save_images:
            image_dir = paper_images_dir(topic_path, paper.bib_key)
            for filename, content in parsed.images.items():
                image_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / filename
                image_path.write_bytes(content)
                result.artifacts_written.append(image_path)

        if len(parsed.markdown.strip()) < config.marker.parse_pdf_min_chars:
            _flag_review(
                topic_path,
                paper.bib_key,
                "parse_pdf",
                f"L0 shorter than parse_pdf_min_chars ({len(parsed.markdown.strip())} < {config.marker.parse_pdf_min_chars})",
            )

        result.processed.append(paper.bib_key)
        _log(logger, "processed", paper.bib_key, str(l0_path), page_count=parsed.page_count)
        _report_progress(progress_callback, index, total, paper, "processed")

    result.duration_seconds = time.monotonic() - started
    return result


def _select_papers(topic_path: Path, bib_key: str | None, limit: int | None) -> list[PaperRow]:
    if bib_key is not None:
        papers = [get_paper(topic_path, bib_key)]
    else:
        papers = list(iter_included(topic_path))
    if limit is not None:
        papers = papers[:limit]
    return papers


def _convert_with_retry(backend: MarkerBackend, pdf_path: Path):
    try:
        return _convert_quietly(backend, pdf_path)
    except Exception:
        return _convert_quietly(backend, pdf_path)


def _convert_quietly(backend: MarkerBackend, pdf_path: Path):
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            return backend.convert(pdf_path)


def _report_progress(
    progress_callback: Callable[[int, int, PaperRow, str], None] | None,
    index: int,
    total: int,
    paper: PaperRow,
    status: str,
) -> None:
    if progress_callback is not None:
        progress_callback(index, total, paper, status)


def _flag_review(topic_path: Path, bib_key: str, op_name: str, reason: str) -> None:
    path = review_needed_csv(topic_path)
    path_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bib_key", "op_name", "reason"])
        if not path_exists:
            writer.writeheader()
        writer.writerow({"bib_key": bib_key, "op_name": op_name, "reason": reason})


def _run_logger(topic_path: Path) -> tuple[logging.Logger, Path]:
    directory = runs_dir(topic_path)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"parse_pdf_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logger = logging.getLogger(f"survey_system.parse_pdf.{id(log_path)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger, log_path


def _log(
    logger: logging.Logger,
    event: str,
    bib_key: str,
    detail: str,
    **extra: object,
) -> None:
    payload = {"event": event, "bib_key": bib_key, "detail": detail}
    payload.update(extra)
    logger.info(json.dumps(payload))
