from pathlib import Path

from scripts.import_official_sample import chinese_number, parse_company_law

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_chinese_number() -> None:
    assert chinese_number("一") == 1
    assert chinese_number("一百零八") == 108
    assert chinese_number("二百六十六") == 266


def test_parse_official_company_law_snapshot() -> None:
    articles = parse_company_law(
        REPO_ROOT / "data/official/company-law-2023/company-law-2023.html"
    )
    assert len(articles) == 266
    assert articles[0]["number"] == 1
    assert articles[-1]["number"] == 266
    assert "规范公司的组织和行为" in articles[0]["text"]


def test_article_266_does_not_swallow_trailing_page_boilerplate() -> None:
    """Regression guard: article 266 is the last article, so it has no
    following article marker to bound it. Without the '关联文件' boilerplate
    cut, its text would swallow the rest of the scraped page — related-doc
    links, video widgets, footer nav, and inline <script>/<style> bodies
    (html.parser emits script/style content via handle_data by default)."""
    articles = parse_company_law(
        REPO_ROOT / "data/official/company-law-2023/company-law-2023.html"
    )
    article_266 = next(a for a in articles if a["number"] == 266)
    text = article_266["text"]
    assert text.endswith("具体实施办法由国务院规定。")
    assert "关联文件" not in text
    assert "script" not in text
    assert "友情链接" not in text
    assert len(text) < 300


def test_article_121_audit_committee_threshold_text_is_intact() -> None:
    """Regression guard for scripts/promote_gov_aud_002.py: GOV-AUD-002's real
    source binding depends on Article 121 genuinely containing the '3 or
    more members' floor — if a future re-scrape or re-parse ever silently
    changed this text, the rule's citation would quietly go stale."""
    articles = parse_company_law(
        REPO_ROOT / "data/official/company-law-2023/company-law-2023.html"
    )
    article_121 = next(a for a in articles if a["number"] == 121)
    assert "审计委员会成员为三名以上" in article_121["text"]
    # The independence qualifier is deliberately NOT implemented by
    # GOV-AUD-002 (see that rule's promotion script docstring) — assert its
    # real wording too, so anyone tempted to bind GOV-AUD-003 here sees why
    # "not holding other posts" isn't the same claim as "independent director".
    assert "过半数成员不得在公司担任除董事以外的其他职务" in article_121["text"]
