from pathlib import Path

import pytest

from scripts.document_extraction import extract_text
from scripts.regulatory_source_parsers import (
    parse_dotted_hierarchical_text,
    parse_sequential_numbered_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_parse_sequential_numbered_text_for_governance_code() -> None:
    text = extract_text(REPO_ROOT / "data/official/csrc-governance-2025/csrc-governance-2025.pdf")
    articles = parse_sequential_numbered_text(text)
    assert len(articles) == 101
    assert articles[0]["article_no"] == "1"
    assert articles[-1]["article_no"] == "101"
    assert articles[0]["chapter_no"] == "第一章 总则"
    assert "为规范上市公司运作" in articles[0]["text"]


def test_parse_sequential_numbered_text_for_independent_director_measures() -> None:
    text = extract_text(REPO_ROOT / "data/official/csrc-id-2023/csrc-id-2023.pdf")
    articles = parse_sequential_numbered_text(text)
    assert len(articles) == 48
    assert articles[0]["article_no"] == "1"
    assert articles[-1]["article_no"] == "48"
    # Regression guard for future rule-source binding to independence
    # requirements — locks the actual defining text, not a paraphrase.
    definition = next(a for a in articles if a["article_no"] == "2")
    assert "不在上市公司担任除董事外的其他职" in definition["text"]


def test_parse_sequential_numbered_text_raises_when_no_articles_found() -> None:
    with pytest.raises(ValueError, match="中文数字连续编号"):
        parse_sequential_numbered_text("这段文本没有任何条文标记。")


def test_parse_dotted_hierarchical_text_for_sse_listing_rules() -> None:
    text = extract_text(REPO_ROOT / "data/official/sse-list-2026/sse-list-2026.docx")
    articles = parse_dotted_hierarchical_text(text)
    assert len(articles) == 521
    assert articles[0]["article_no"] == "1.1"
    assert articles[0]["chapter_no"] == "第一章  总  则"
    assert articles[-1]["article_no"] == "16.3"
    board_secretary = next(a for a in articles if a["article_no"] == "4.4.1")
    assert "董事会秘书" in board_secretary["text"]
    assert board_secretary["chapter_no"] == "第四章  公司治理"


def test_parse_dotted_hierarchical_text_for_self_regulation_guideline() -> None:
    text = extract_text(REPO_ROOT / "data/official/sse-gov-2026/sse-gov-2026.docx")
    articles = parse_dotted_hierarchical_text(text)
    assert len(articles) == 295
    assert articles[0]["article_no"] == "1.1"


def test_parse_dotted_hierarchical_text_for_szse_listing_rules() -> None:
    text = extract_text(REPO_ROOT / "data/official/szse-list-2026/szse-list-2026.pdf")
    articles = parse_dotted_hierarchical_text(text)
    assert len(articles) == 520
    assert articles[0]["article_no"] == "1.1"
    assert articles[-1]["article_no"] == "16.3"
    # TOC lists every chapter with dot-leaders before the real body starts —
    # regression guard that chapter assignment resolves to the real body
    # heading (chronologically last-before-article), not a TOC entry.
    assert articles[0]["chapter_no"] == "第一章 总 则"


def test_parse_dotted_hierarchical_text_does_not_split_on_wrapped_cross_references() -> None:
    """Regression guard: PDF line-wrapping can break '第9.3.1条' across two
    lines, landing '9.3.1' at a line start that looks like a real article
    marker. Real article starts are never immediately followed by '条'."""
    text = extract_text(REPO_ROOT / "data/official/szse-list-2026/szse-list-2026.pdf")
    articles = parse_dotted_hierarchical_text(text)
    numbers = [a["article_no"] for a in articles]
    assert len(numbers) == len(set(numbers))
    risk_prevention = next(a for a in articles if a["article_no"] == "9.3.1")
    assert risk_prevention["text"].startswith("9.3.1 上市公司出现下列情形之一的")


def test_parse_dotted_hierarchical_text_raises_when_no_articles_found() -> None:
    with pytest.raises(ValueError, match="层级编号"):
        parse_dotted_hierarchical_text("这段文本没有任何条文标记。")
