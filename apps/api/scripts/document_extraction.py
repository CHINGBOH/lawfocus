"""Text extraction for non-HTML official source snapshots (PDF/DOCX).

`import_official_sample.py`'s HTML parser only works when the source page
itself is the article text (company law). Regulatory/exchange sources are
distributed as PDF or DOCX attachments instead — this module extracts plain
text from those so the same downstream article-splitting logic can run on
the result. Extraction is pure text-in/text-out and reproducible (no
one-off manual conversion).
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from docx import Document


def extract_pdf_text(path: Path) -> str:
    # pdfplumber (pdfminer.six-based) reconstructs text runs correctly on
    # these government PDFs; pypdf was tried first and silently garbled at
    # least one real source into one-character-per-line output with no
    # error — a much worse failure mode than an exception would have been.
    with pdfplumber.open(str(path)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def extract_docx_text(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    raise ValueError(f"unsupported document type: {suffix}")
