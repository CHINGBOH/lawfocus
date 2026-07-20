"""Import the five regulatory/exchange sources added in B2 (01号文档 P0 list).

Run from ``apps/api`` with ``uv run python -m scripts.import_regulatory_sources``.
Idempotent — reruns don't duplicate documents, versions, or articles.
Records remain ``UNVERIFIED`` until a legal reviewer confirms the snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Article, ArticleVersion, LegalDocument, LegalVersion
from scripts.document_extraction import extract_text
from scripts.import_official_sample import MANIFEST_PATH, REPO_ROOT, _one_or_create, _verify_sources
from scripts.regulatory_source_parsers import (
    parse_dotted_hierarchical_text,
    parse_sequential_numbered_text,
)


@dataclass(frozen=True)
class _DocumentMeta:
    document_code: str
    document_name: str
    issuer: str
    version_name: str
    document_type: str


_DOCUMENT_META: dict[str, _DocumentMeta] = {
    "CSRC-GOV-2025": _DocumentMeta(
        document_code="CSRC-GOV-2025", document_name="上市公司治理准则",
        issuer="中国证券监督管理委员会", version_name="2025年发布", document_type="REGULATION",
    ),
    "CSRC-ID-2023": _DocumentMeta(
        document_code="CSRC-ID-2023", document_name="上市公司独立董事管理办法",
        issuer="中国证券监督管理委员会", version_name="2023年发布", document_type="REGULATION",
    ),
    "SSE-LIST-2026": _DocumentMeta(
        document_code="SSE-LIST-2026", document_name="上海证券交易所股票上市规则",
        issuer="上海证券交易所", version_name="2026年4月修订", document_type="EXCHANGE_RULE",
    ),
    "SSE-GOV-2026": _DocumentMeta(
        document_code="SSE-GOV-2026", document_name="上海证券交易所上市公司自律监管指引第1号——规范运作",
        issuer="上海证券交易所", version_name="2026年4月修订", document_type="EXCHANGE_RULE",
    ),
    "SZSE-LIST-2026": _DocumentMeta(
        document_code="SZSE-LIST-2026", document_name="深圳证券交易所股票上市规则",
        issuer="深圳证券交易所", version_name="2026年修订", document_type="EXCHANGE_RULE",
    ),
}

_PARSERS = {
    "chinese_numeral_sequential": parse_sequential_numbered_text,
    "dotted_hierarchical": parse_dotted_hierarchical_text,
}


def _import_source(session: Session, source: dict) -> tuple[str, int]:
    meta = _DOCUMENT_META[source["code"]]
    parser = _PARSERS[source["article_numbering"]]

    text = extract_text(REPO_ROOT / source["local_file"])
    articles = parser(text)
    if not articles:
        raise ValueError(f"{source['code']}: 未解析出任何条文")

    document = _one_or_create(
        session, LegalDocument, code=meta.document_code,
        defaults={"name": meta.document_name, "document_type": meta.document_type,
                  "issuer": meta.issuer, "jurisdiction": "中华人民共和国",
                  "source_url": source["authority_url"], "source_hash": source["sha256"]},
    )
    version = _one_or_create(
        session, LegalVersion, document_id=document.id, version_name=meta.version_name,
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
    return meta.document_code, len(articles)


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = _verify_sources(manifest)
    results = []
    with SessionLocal() as session:
        for code in _DOCUMENT_META:
            document_code, article_count = _import_source(session, sources[code])
            results.append({"document_code": document_code, "article_count": article_count})
        session.commit()
    print(json.dumps({"status": "UNVERIFIED", "imported": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
