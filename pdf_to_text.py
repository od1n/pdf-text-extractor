#!/usr/bin/env python3
"""
pdf_to_text.py — Extract clean plain text from a PDF with a verification report.

Why two engines?
    A single extractor can silently drop characters (ligatures, hyphenated
    words, rotated text). This tool extracts the same file with TWO
    independent engines (Poppler's pdftotext, which keeps line breaks and
    paragraph spacing, and pdfplumber), compares them page by page and reports
    any difference, so nothing is missed or added without being flagged.

What you get
    <name>.txt          plain text, one form-feed (\\f) between pages by default
    <name>_report.txt   per-page word counts for both engines, similarity score,
                        pages that look scanned (no text layer) and would need OCR

Usage
    python pdf_to_text.py input.pdf
    python pdf_to_text.py input.pdf --output out.txt --page-sep blank --ocr

Requirements
    pip install pdfplumber
    Poppler (pdftotext) on PATH — optional but recommended for the cross-check
    Tesseract on PATH — only if --ocr is used for scanned pages
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import subprocess
import sys
from pathlib import Path

import pdfplumber


# --------------------------------------------------------------------------- #
# Extraction engines
# --------------------------------------------------------------------------- #
def extract_with_pdfplumber(pdf_path: Path) -> list[str]:
    """Return one string per page using pdfplumber (independent cross-check)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
            pages.append(text)
    return pages


def extract_with_pdftotext(pdf_path: Path) -> list[str] | None:
    """Return one string per page using Poppler's pdftotext, or None if absent."""
    if shutil.which("pdftotext") is None:
        return None
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    )
    pages = result.stdout.split("\f")
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]
    return pages


def ocr_page(pdf_path: Path, page_number: int) -> str:
    """OCR a single page (1-based) with Tesseract. Used only for scanned pages."""
    if shutil.which("pdftoppm") is None or shutil.which("tesseract") is None:
        raise RuntimeError("OCR needs Poppler (pdftoppm) and Tesseract on PATH")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(["pdftoppm", "-r", "300", "-f", str(page_number), "-l", str(page_number),
                        "-png", str(pdf_path), str(prefix)], check=True)
        png = next(Path(tmp).glob("page*.png"))
        out = subprocess.run(["tesseract", str(png), "-", "--psm", "6"],
                             capture_output=True, text=True, check=True)
        return out.stdout


# --------------------------------------------------------------------------- #
# Cleaning and comparison
# --------------------------------------------------------------------------- #
def clean(text: str) -> str:
    """Normalise whitespace without touching content.

    - strips trailing spaces on each line
    - collapses 3+ blank lines into 2 (keeps paragraph spacing)
    - normalises Windows line endings
    """
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    out, blank = [], 0
    for ln in lines:
        if ln.strip() == "":
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip("\n")


def words(text: str) -> list[str]:
    return text.split()


def similarity(a: str, b: str) -> float:
    """Word-level similarity ratio between two texts (1.0 = identical)."""
    return difflib.SequenceMatcher(None, words(a), words(b), autojunk=False).ratio()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="Input PDF")
    ap.add_argument("--output", "-o", help="Output .txt (default: <pdf name>.txt next to the PDF)")
    ap.add_argument("--page-sep", choices=("formfeed", "blank", "none"), default="formfeed",
                    help="Separator between pages in the .txt (default: form feed)")
    ap.add_argument("--ocr", action="store_true", help="OCR pages that have no text layer")
    ap.add_argument("--min-words", type=int, default=5,
                    help="Pages with fewer words than this are flagged as possibly scanned")
    args = ap.parse_args(argv)

    pdf_path = Path(args.pdf)
    out_path = Path(args.output) if args.output else pdf_path.with_suffix(".txt")
    report_path = out_path.with_name(out_path.stem + "_report.txt")

    # pdftotext keeps paragraph spacing faithfully, so it is the primary engine
    # when available; pdfplumber is the independent cross-check (and the
    # fallback when Poppler is not installed).
    poppler = extract_with_pdftotext(pdf_path)
    plumber = extract_with_pdfplumber(pdf_path)
    if poppler is not None:
        primary, secondary, engine_line = poppler, plumber, "pdftotext (primary) + pdfplumber (cross-check)"
    else:
        primary, secondary, engine_line = plumber, None, "pdfplumber (pdftotext not found, no cross-check)"

    final_pages, report = [], []
    report.append(f"File: {pdf_path.name}")
    report.append(f"Pages: {len(primary)}")
    report.append(f"Engines: {engine_line}")
    report.append("")
    report.append(f"{'page':>4} {'words_A':>8} {'words_B':>8} {'similarity':>10}  status")

    flagged = 0
    for i, text_a in enumerate(primary, start=1):
        text_a = clean(text_a)
        text_b = clean(secondary[i - 1]) if secondary and i - 1 < len(secondary) else None
        wa = len(words(text_a))
        wb = len(words(text_b)) if text_b is not None else -1
        status = "OK"

        if wa < args.min_words and (text_b is None or wb < args.min_words):
            if args.ocr:
                text_a = clean(ocr_page(pdf_path, i))
                wa = len(words(text_a))
                status = "OCR"
            else:
                status = "SCANNED? (no text layer, run with --ocr)"
                flagged += 1
        elif text_b is not None:
            sim = similarity(text_a, text_b)
            if sim < 0.97:
                status = f"REVIEW (engines differ, similarity {sim:.3f})"
                flagged += 1
            # if the cross-check engine captured clearly more words, use it
            if wb > wa * 1.05:
                text_a, status = text_b, status + " -> used cross-check engine"
        final_pages.append(text_a)
        report.append(f"{i:>4} {wa:>8} {wb:>8} {'-' if text_b is None else f'{similarity(text_a, text_b):.3f}':>10}  {status}")

    sep = {"formfeed": "\f", "blank": "\n\n", "none": "\n"}[args.page_sep]
    out_path.write_text(sep.join(final_pages) + "\n", encoding="utf-8")

    total_words = sum(len(words(p)) for p in final_pages)
    report.append("")
    report.append(f"Total words: {total_words}")
    report.append(f"Pages flagged for review: {flagged}")
    report.append(f"Output: {out_path.name}")
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
