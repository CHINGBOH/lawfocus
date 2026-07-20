"""Article-splitting for the regulatory/exchange sources added in B2.

Two distinct numbering conventions exist among these sources (confirmed by
extracting and inspecting the real downloaded files, not assumed):

- CSRC-GOV-2025 (治理准则) / CSRC-ID-2023 (独董办法): continuous Chinese-numeral
  numbering ("第一条", "第一百零一条"), same convention as company law —
  reuses `ARTICLE_MARKER`/`CHAPTER_MARKER`/`chinese_number` from
  `import_official_sample`.
- SSE-LIST-2026 / SSE-GOV-2026 / SZSE-LIST-2026 (交易所规则/指引): dotted
  hierarchical numbering ("1.1", "4.4.1", "16.3"), with no "第...条" prefix
  in the body — a different marker is required.

Unlike the HTML-scraped company law page, PDF/DOCX extraction has no
trailing page-chrome problem (confirmed empirically: the last article in
each of these five sources ends cleanly at document end), so neither parser
here needs a boilerplate-cutting step.
"""

from __future__ import annotations

import re

from scripts.import_official_sample import ARTICLE_MARKER, CHAPTER_MARKER, chinese_number

DOTTED_ARTICLE_MARKER = re.compile(r"^(\d+\.\d+(?:\.\d+)?)\s+(?!条)(?=\S)", re.MULTILINE)
DOTTED_CHAPTER_MARKER = re.compile(r"^第[一二三四五六七八九十百]+章[^\n]*", re.MULTILINE)


def parse_sequential_numbered_text(text: str) -> list[dict[str, str | int | None]]:
    """Continuous Chinese-numeral article numbering (regulatory commission rules)."""
    starts = list(ARTICLE_MARKER.finditer(text))
    if not starts:
        raise ValueError("未在文本中找到中文数字连续编号的条文")

    articles: list[dict[str, str | int | None]] = []
    for index, marker in enumerate(starts):
        number = chinese_number(marker.group(1))
        if number != len(articles) + 1:
            continue
        end = next(
            (candidate.start() for candidate in starts[index + 1:]
             if chinese_number(candidate.group(1)) == number + 1),
            len(text),
        )
        previous_chapters = list(CHAPTER_MARKER.finditer(text[: marker.start()]))
        chapter = previous_chapters[-1].group(0).strip() if previous_chapters else None
        articles.append({
            "number": number,
            "article_no": str(number),
            "chapter_no": chapter,
            "text": text[marker.start():end].strip(),
        })
    return articles


def parse_dotted_hierarchical_text(text: str) -> list[dict[str, str | int | None]]:
    """Dotted hierarchical article numbering (exchange listing rules/guidelines).

    Numbers aren't a simple linear counter (1.1, 1.2, 2.1.1, ...), so unlike
    the sequential parser this trusts document order rather than validating
    continuity — duplicate/out-of-order numbers would indicate a genuinely
    different document structure, not a fixable-by-us assumption.
    """
    starts = list(DOTTED_ARTICLE_MARKER.finditer(text))
    if not starts:
        raise ValueError("未在文本中找到「X.Y」式层级编号的条文")

    seen: set[str] = set()
    articles: list[dict[str, str | int | None]] = []
    for index, marker in enumerate(starts):
        article_no = marker.group(1)
        if article_no in seen:
            raise ValueError(f"条号重复，解析结果不可信：{article_no}")
        seen.add(article_no)
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        previous_chapters = list(DOTTED_CHAPTER_MARKER.finditer(text[: marker.start()]))
        chapter = previous_chapters[-1].group(0).strip() if previous_chapters else None
        articles.append({
            "number": None,
            "article_no": article_no,
            "chapter_no": chapter,
            "text": text[marker.start():end].strip(),
        })
    return articles
