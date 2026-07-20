from pathlib import Path

import pytest

from scripts.document_extraction import extract_docx_text, extract_pdf_text, extract_text

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_extract_pdf_text_finds_known_anchor() -> None:
    text = extract_pdf_text(REPO_ROOT / "data/official/csrc-governance-2025/csrc-governance-2025.pdf")
    assert "上市公司治理准则" in text
    assert "第一条" in text


def test_extract_pdf_text_for_independent_director_measures() -> None:
    text = extract_pdf_text(REPO_ROOT / "data/official/csrc-id-2023/csrc-id-2023.pdf")
    assert "上市公司独立董事管理办法" in text


def test_extract_pdf_text_for_szse_listing_rules() -> None:
    text = extract_pdf_text(REPO_ROOT / "data/official/szse-list-2026/szse-list-2026.pdf")
    assert "深圳证券交易所股票上市规则" in text


def test_extract_docx_text_finds_known_anchor() -> None:
    text = extract_docx_text(REPO_ROOT / "data/official/sse-list-2026/sse-list-2026.docx")
    assert "上海证券交易所股票上市规则" in text
    # Exchange listing rules use dotted hierarchical numbering ("4.4.1"),
    # not the continuous Chinese-numeral numbering company law uses — the
    # existing ARTICLE_MARKER regex in import_official_sample.py cannot
    # split these; a separate parser is required (tracked as B2).
    assert "4.4.1" in text


def test_extract_docx_text_for_self_regulation_guideline() -> None:
    text = extract_docx_text(REPO_ROOT / "data/official/sse-gov-2026/sse-gov-2026.docx")
    assert "自律监管指引" in text


def test_extract_text_dispatches_by_suffix() -> None:
    pdf_text = extract_text(REPO_ROOT / "data/official/csrc-governance-2025/csrc-governance-2025.pdf")
    docx_text = extract_text(REPO_ROOT / "data/official/sse-list-2026/sse-list-2026.docx")
    assert "上市公司治理准则" in pdf_text
    assert "上海证券交易所股票上市规则" in docx_text


def test_extract_text_rejects_unsupported_suffix(tmp_path: Path) -> None:
    bogus = tmp_path / "source.txt"
    bogus.write_text("not a real document")
    with pytest.raises(ValueError, match="unsupported document type"):
        extract_text(bogus)
