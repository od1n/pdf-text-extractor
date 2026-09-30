# PDF to plain text, with verification

Extracts every word of a PDF into a clean `.txt` that mirrors the source line
breaks and paragraph spacing, and writes a **verification report** so you can
confirm nothing was missed or added.

## Why two engines

A single extractor can silently drop characters (ligatures, hyphenated words,
rotated text). This tool runs two independent engines on the same file —
Poppler's `pdftotext` (keeps layout and paragraph spacing) and `pdfplumber` —
compares them **page by page** and flags any page where they disagree.
Pages with no text layer (scanned images) are detected and, with `--ocr`,
recovered with Tesseract.

## Quick start

```bash
pip install -r requirements.txt        # pdfplumber
# Poppler (pdftotext, pdftoppm) and Tesseract on PATH — see below

python pdf_to_text.py sample/sample_text.pdf
python pdf_to_text.py document.pdf --output document.txt --page-sep blank
python pdf_to_text.py scanned.pdf --ocr
```

## Options

| Option | Meaning |
|---|---|
| `--output, -o` | Output `.txt` (default: same name as the PDF) |
| `--page-sep` | `formfeed` (default, `\f` between pages), `blank` (empty line) or `none` |
| `--ocr` | OCR pages that have no text layer (needs Poppler + Tesseract) |
| `--min-words` | Pages with fewer words are treated as possibly scanned (default 5) |

## Output

* `document.txt` — plain text, UTF-8, no headings or formatting added.
* `document_report.txt` — per page: word count from each engine, similarity
  score and status (`OK`, `REVIEW`, `SCANNED?`, `OCR`), total words and the
  number of pages that need a human look.

Example report (included in `sample/`):

```
page  words_A  words_B similarity  status
   1      103      103      1.000  OK
   2      102      102      1.000  OK
   3       91       91      1.000  OK

Total words: 296
Pages flagged for review: 0
```

## Installing the system tools

* Windows: Poppler from https://github.com/oschwartz10612/poppler-windows/releases (add `bin` to PATH); Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
* macOS: `brew install poppler tesseract`
* Debian/Ubuntu: `sudo apt install poppler-utils tesseract-ocr`

Without Poppler the tool still works with `pdfplumber` alone (no cross-check).
