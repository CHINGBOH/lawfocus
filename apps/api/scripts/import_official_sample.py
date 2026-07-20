"""Import an official law snapshot and one real listed-company sample.

The importer is intentionally conservative: parsed records remain UNVERIFIED
until a legal reviewer checks the source snapshot and extracted facts.
Run from ``apps/api`` with ``uv run python -m scripts.import_official_sample``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import (
    Article,
    ArticleVersion,
    Evidence,
    Fact,
    FactEvidence,
    LegalDocument,
    LegalSubject,
    LegalVersion,
    Organization,
    RoleAssignment,
    RoleType,
    Tenant,
)
from app.models.enums import SubjectType

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "data/official/manifest.json"
ARTICLE_MARKER = re.compile(r"第([一二三四五六七八九十百零〇两]+)条")
CHAPTER_MARKER = re.compile(r"第[一二三四五六七八九十百零〇两]+章\s*[^第]{0,30}")


class _TextExtractor(HTMLParser):
    """html.parser treats <script>/<style> bodies as CDATA and still emits
    them via handle_data — without skipping them, embedded page scripts get
    flattened into the same text stream as the statutory content."""

    _SKIPPED_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip())


def chinese_number(value: str) -> int:
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100}
    total = current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in units:
            total += (current or 1) * units[char]
            current = 0
    return total + current


def parse_company_law(path: Path) -> list[dict[str, str | int | None]]:
    parser = _TextExtractor()
    parser.feed(path.read_text(encoding="utf-8"))
    text = re.sub(r"\s+", " ", " ".join(parser.parts))
    # The source page appends a "关联文件" (related documents) sidebar right
    # after the statutory text ends, followed by unrelated page chrome
    # (video widgets, related-doc cards, footer nav). Every article except
    # the last is bounded by the next article's marker, but the last one
    # (266) has nothing to stop at and would otherwise swallow everything
    # to the end of the page. This marker is unique in the source file
    # (verified: exactly one occurrence, right at that boundary).
    boilerplate_start = text.find("关联文件")
    if boilerplate_start != -1:
        text = text[:boilerplate_start]
    starts = list(ARTICLE_MARKER.finditer(text))
    if not starts:
        raise ValueError("未在官方网页快照中找到公司法条文")

    articles: list[dict[str, str | int | None]] = []
    for index, marker in enumerate(starts):
        number = chinese_number(marker.group(1))
        # Ignore incidental article references before the actual body and duplicates.
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
    if len(articles) != 266:
        raise ValueError(f"公司法条文数量异常：期望266，实际{len(articles)}")
    return articles


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one_or_create(session: Session, model, *, defaults: dict | None = None, **lookup):
    row = session.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if row is not None:
        return row
    row = model(**lookup, **(defaults or {}))
    session.add(row)
    session.flush()
    return row


def _verify_sources(manifest: dict) -> dict[str, dict]:
    sources = {item["code"]: item for item in manifest["sources"]}
    for item in sources.values():
        local_file = REPO_ROOT / item["local_file"]
        actual = _sha256(local_file)
        if actual != item["sha256"]:
            raise ValueError(f"来源哈希不匹配：{local_file}，实际 {actual}")
    return sources


def _import_law(session: Session, source: dict) -> tuple[LegalDocument, int]:
    articles = parse_company_law(REPO_ROOT / source["local_file"])
    document = _one_or_create(
        session, LegalDocument, code="PRC-COMPANY-LAW",
        defaults={"name": "中华人民共和国公司法", "document_type": "LAW",
                  "issuer": "全国人民代表大会常务委员会", "jurisdiction": "中华人民共和国",
                  "source_url": source["authority_url"], "source_hash": source["sha256"]},
    )
    version = _one_or_create(
        session, LegalVersion, document_id=document.id, version_name="2023年修订",
        defaults={"promulgated_at": date.fromisoformat(source["promulgated_at"]),
                  "effective_from": date.fromisoformat(source["effective_from"]),
                  "effective_to": None, "status": "UNVERIFIED",
                  "version_hash": source["sha256"]},
    )
    for parsed in articles:
        article = _one_or_create(
            session, Article, document_id=document.id, article_no=parsed["article_no"]
        )
        _one_or_create(
            session, ArticleVersion, article_id=article.id, legal_version_id=version.id,
            defaults={"chapter_no": parsed["chapter_no"], "section_no": None,
                      "article_text": parsed["text"], "normalized_text": parsed["text"],
                      "valid_from": date.fromisoformat(source["effective_from"]), "valid_to": None},
        )
    return document, len(articles)


def _role(session: Session, code: str, name: str) -> RoleType:
    return _one_or_create(session, RoleType, code=code, defaults={"name": name})


def _assign(session: Session, person, role, company, organization, valid_from: date) -> None:
    _one_or_create(
        session, RoleAssignment, person_id=person.id, role_type_id=role.id,
        company_id=company.id, organization_id=organization.id if organization else None,
        valid_from=valid_from, defaults={"valid_to": None},
    )


def _evidence(session: Session, tenant, source: dict, *, title: str, page: int, quote: str):
    return _one_or_create(
        session, Evidence, tenant_id=tenant.id, title=title, source_hash=source["sha256"],
        defaults={"evidence_type": "ANNUAL_REPORT", "source_url": source["content_url"],
                  "source_file": source["local_file"], "page_no": page, "quote_text": quote,
                  "published_at": date.fromisoformat(source["published_at"])},
    )


def _fact(session: Session, tenant, company, *, fact_type: str, predicate: str,
          value: dict, valid_from: date, evidence: Evidence):
    row = _one_or_create(
        session, Fact, tenant_id=tenant.id, company_id=company.id,
        fact_type=fact_type, predicate=predicate, valid_from=valid_from,
        defaults={"subject_ref": company.id, "object_value": value, "valid_to": None},
    )
    if row.object_value != value:
        raise ValueError(f"已有事实与本次导入冲突：{fact_type}.{predicate}")
    _one_or_create(
        session, FactEvidence, fact_id=row.id, evidence_id=evidence.id,
        defaults={"support_type": "DIRECT", "confidence": 1.0},
    )
    return row


def _import_company(session: Session, tenant: Tenant, source: dict) -> LegalSubject:
    reporting_date = date.fromisoformat(source["reporting_date"])
    company = session.execute(select(LegalSubject).where(
        LegalSubject.subject_type == SubjectType.LISTED_COMPANY,
        LegalSubject.name == "贵州茅台酒股份有限公司",
    )).scalar_one_or_none()
    if company is None:
        company = LegalSubject(subject_type=SubjectType.LISTED_COMPANY,
                               name="贵州茅台酒股份有限公司", unified_credit_code=None,
                               listed=True, exchange="SSE:600519")
        session.add(company)
        session.flush()

    board = _one_or_create(session, Organization, company_id=company.id,
                           organization_type="BOARD", defaults={"name": "董事会"})
    audit = _one_or_create(session, Organization, company_id=company.id,
                           organization_type="AUDIT_COMMITTEE", defaults={"name": "审计委员会"})
    director = _role(session, "DIRECTOR", "董事")
    independent = _role(session, "INDEPENDENT_DIRECTOR", "独立董事")
    employee_director = _role(session, "EMPLOYEE_DIRECTOR", "职工董事")
    audit_member = _role(session, "AUDIT_COMMITTEE_MEMBER", "审计委员会成员")

    directors = [
        ("陈华", date(2025, 11, 28), None), ("王莉", date(2023, 9, 7), None),
        ("郭田勇", date(2022, 6, 16), independent), ("盛雷鸣", date(2022, 6, 16), independent),
        ("王鑫", date(2023, 12, 6), independent), ("周雪", date(2025, 5, 19), None),
        ("韦芳", date(2024, 10, 18), employee_director),
    ]
    people: dict[str, LegalSubject] = {}
    for name, started, special_role in directors:
        person = _one_or_create(session, LegalSubject, subject_type=SubjectType.PERSON, name=name,
                                defaults={"unified_credit_code": None, "listed": False,
                                          "exchange": None})
        people[name] = person
        _assign(session, person, director, company, board, started)
        if special_role:
            _assign(session, person, special_role, company, board, started)
    for name in ("王鑫", "郭田勇", "盛雷鸣"):
        # The report proves membership at year-end, but does not provide appointment dates.
        _assign(session, people[name], audit_member, company, audit, reporting_date)

    governance_ev = _evidence(
        session, tenant, source, title="贵州茅台2025年报：董事会构成", page=23,
        quote="公司董事会目前由7名董事组成，其中3名为独立董事，1名为职工董事；董事会下设审计委员会。",
    )
    audit_ev = _evidence(
        session, tenant, source, title="贵州茅台2025年报：审计委员会成员", page=29,
        quote="审计委员会成员：王鑫、郭田勇、盛雷鸣。",
    )
    _fact(session, tenant, company, fact_type="BOARD_COMPOSITION",
          predicate="independent_director_count", value={"total": 7, "independent": 3},
          valid_from=reporting_date, evidence=governance_ev)
    _fact(session, tenant, company, fact_type="AUDIT_COMMITTEE",
          predicate="member_composition",
          value={"total": 3, "independent": 3, "members": ["王鑫", "郭田勇", "盛雷鸣"]},
          valid_from=reporting_date, evidence=audit_ev)
    _fact(session, tenant, company, fact_type="PUBLIC_DISCLOSURE", predicate="stock_identity",
          value={"exchange": "SSE", "stock_code": "600519"},
          valid_from=reporting_date, evidence=governance_ev)
    return company


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = _verify_sources(manifest)
    with SessionLocal() as session:
        tenant = session.execute(select(Tenant).where(Tenant.code == "demo-tenant")).scalar_one_or_none()
        if tenant is None:
            raise SystemExit("缺少 demo-tenant；请先执行项目 seed 命令。")
        document, article_count = _import_law(session, sources["PRC-COMPANY-LAW-2023"])
        company = _import_company(session, tenant, sources["SSE-600519-ANNUAL-REPORT-2025"])
        session.commit()
        print(json.dumps({"status": "UNVERIFIED", "law_document_id": str(document.id),
                          "article_count": article_count, "company_id": str(company.id),
                          "company": company.name, "reporting_date": "2025-12-31"},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
