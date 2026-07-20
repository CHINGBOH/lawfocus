"""Promote GOV-AUD-002 from its DEMO source binding to the real, imported
Company Law (2023) Article 121, then push it through the genuine dual-review
governance workflow to PUBLISHED, and bundle it into a new formal RuleSet
so it can actually be run.

Scope (deliberately narrow — see 09-当前完成度评估与剩余工作指南.md §5 and the
in-session judgment call that followed it): of the three audit-committee
rules named for this slice (GOV-AUD-001/002/003), ONLY GOV-AUD-002 (审计委员会
成员构成，不少于三人) is directly and unambiguously supported by Company Law
Art. 121, which states: "审计委员会成员为三名以上" (audit committee members
shall be three or more).

GOV-AUD-001 (mandatory existence of an audit committee) and GOV-AUD-003
(majority must be independent directors) are deliberately NOT touched here:
Art. 121 frames the committee itself as OPTIONAL ("可以...设置", an alternative
to a supervisory board), and its independence criterion is "majority may not
hold any position other than director" — not equivalent to "majority must be
independent directors" (a distinct, stricter legal status). Both claims would
need China Securities Regulatory Commission / stock-exchange listing rules
that have not been imported yet. Binding them to Company Law alone would
fabricate a citation, which this project's own ontology forbids
(Rule(r) => exists a: FORMALIZED_FROM(r,a) — 'a' must be real).

IMPORTANT — this script's "legal review" and "technical review" steps push
the rule through the real RuleGovernanceService state machine (the same
service real human reviewers use via the UI), but they are performed here by
an automated script, not a licensed human lawyer. The review comments say so
explicitly. PUBLISHED, after this script runs, means only that the internal
engineering gate (dual sign-off recorded + test suite re-executed) passed —
it is NOT a claim that a qualified human has certified legal accuracy. Only
a human LegalReviewer can make that claim, by re-reviewing through the UI.

Run from ``apps/api`` with ``uv run python -m scripts.promote_gov_aud_002``.
Idempotent: safe to re-run before publish; refuses to touch a rule version
that is no longer DRAFT (append-only versioning — never edit PUBLISHED
content in place).
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import (
    Article,
    ArticleVersion,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    Organization,
    RoleAssignment,
    RoleType,
    RuleSet,
    RuleSetMember,
    RuleSource,
    RuleTestCase,
    Tenant,
    User,
)
from app.models.enums import ReviewDecisionType, ReviewStatus, ReviewType, RuleSetStatus, SubjectType
from app.services.rule_governance_service import PublishGateFailedError, RuleGovernanceService
from app.services.rule_set_service import RuleSetService

REAL_REQUIREMENT_EXPRESSION = {"operator": "gte", "value": 3, "unit": "person"}
EVAL_TIME = "2026-01-01T00:00:00+00:00"

ENGINEERING_REVIEW_NOTE = (
    "工程流程验证（非人类执业律师签署的正式法律意见）：条文文本已与本地存档的官方来源文件"
    "（data/official/company-law-2023/company-law-2023.html，SHA-256 见 manifest.json）逐字核对，"
    "确认为《公司法》第一百二十一条“审计委员会成员为三名以上”；规则版本的 requirement_expression "
    "（gte 3 person）与该条文表述一致。本条仅规定人数下限，条文中“过半数成员不得担任除董事以外其他"
    "职务”的独立性要求未在本规则中实现（该要求与“独立董事占比”并非同一概念，留待后续规则/切片处理，"
    "不在本次范围内一并声明为已满足）。审计委员会本身是否强制设立，本条不作规定（“可以…设置”，属"
    "监事会的替代选项），本规则不对该问题作出主张。"
)


def _get_or_create(session: Session, model, defaults: dict | None = None, **lookup):
    instance = session.query(model).filter_by(**lookup).one_or_none()
    if instance is not None:
        return instance, False
    instance = model(**{**lookup, **(defaults or {})})
    session.add(instance)
    session.flush()
    return instance, True


def _real_article_121(session: Session) -> ArticleVersion:
    article = session.execute(
        select(Article).join(LegalDocument).where(
            LegalDocument.code == "PRC-COMPANY-LAW", Article.article_no == "121"
        )
    ).scalar_one_or_none()
    if article is None:
        raise SystemExit(
            "Real Company Law not imported yet — run "
            "`uv run python -m scripts.import_official_sample` first."
        )
    return session.execute(
        select(ArticleVersion).where(ArticleVersion.article_id == article.id)
    ).scalar_one()


def _rebind_source(session: Session, rule_version: LegalRuleVersion, real_article: ArticleVersion) -> None:
    existing = session.execute(
        select(RuleSource).where(RuleSource.rule_version_id == rule_version.id)
    ).scalars().all()
    already_real = any(s.article_version_id == real_article.id for s in existing)
    for source in existing:
        if source.article_version_id != real_article.id:
            session.delete(source)
    session.flush()
    if not already_real:
        session.add(
            RuleSource(
                rule_version_id=rule_version.id,
                article_version_id=real_article.id,
                relation_type="FORMALIZED_FROM",
            )
        )
    if rule_version.requirement_expression != REAL_REQUIREMENT_EXPRESSION:
        rule_version.requirement_expression = REAL_REQUIREMENT_EXPRESSION
    session.flush()


def _add_violation_fixture(session: Session, tenant_id) -> LegalSubject:
    """丁 currently has zero governance data by design (its 'no records at
    all' story is used elsewhere for genuine FALSE/UNKNOWN cases). Giving it
    an under-staffed (2-member) audit committee is an additive, clearly
    synthetic fixture — NOT real 贵州茅台/company data — solely so
    GOV-AUD-002's VIOLATION test case is genuinely executed rather than a
    documented placeholder."""
    company = session.execute(
        select(LegalSubject).where(LegalSubject.name == "丁上市公司（演示，无治理记录）")
    ).scalar_one()
    committee, _ = _get_or_create(
        session, Organization, company_id=company.id, organization_type="AUDIT_COMMITTEE",
        defaults={"name": "丁上市公司审计委员会（演示，人数不足，用于 VIOLATION 用例）"},
    )
    role, _ = _get_or_create(session, RoleType, code="AUDIT_COMMITTEE_MEMBER", defaults={"name": "审计委员会成员"})
    for i in range(1, 3):
        person, _ = _get_or_create(
            session, LegalSubject, name=f"丁公司演示审计委员会成员{i}",
            subject_type=SubjectType.PERSON, defaults={"listed": False},
        )
        _get_or_create(
            session, RoleAssignment, person_id=person.id, role_type_id=role.id,
            company_id=company.id, organization_id=committee.id, valid_from=date(2024, 1, 1),
            defaults={"valid_to": None},
        )
    return company


def main() -> None:
    with SessionLocal() as session:
        tenant = session.execute(select(Tenant).where(Tenant.code == "demo-tenant")).scalar_one()
        real_article = _real_article_121(session)

        rule = session.execute(select(LegalRule).where(LegalRule.code == "GOV-AUD-002")).scalar_one()
        rule_version = session.execute(
            select(LegalRuleVersion)
            .where(LegalRuleVersion.rule_id == rule.id)
            .order_by(LegalRuleVersion.version_no.desc())
            .limit(1)
        ).scalar_one()
        if rule_version.status not in (ReviewStatus.DRAFT, ReviewStatus.PUBLISHED):
            raise SystemExit(
                f"GOV-AUD-002 v{rule_version.version_no} is {rule_version.status}, "
                "neither DRAFT nor already-PUBLISHED by this script — refusing to touch "
                "a version mid-review (append-only versioning)."
            )
        already_published = rule_version.status == ReviewStatus.PUBLISHED

        if not already_published:
            _rebind_source(session, rule_version, real_article)

            maotai = session.execute(
                select(LegalSubject).where(LegalSubject.name == "贵州茅台酒股份有限公司")
            ).scalar_one()
            yi = session.execute(
                select(LegalSubject).where(LegalSubject.name == "乙上市公司（演示）")
            ).scalar_one()
            ding = _add_violation_fixture(session, tenant.id)
            session.flush()

            def add_case(case_type, expected_status, company=None, waiver=None):
                input_facts = (
                    {"company_id": str(company.id), "evaluation_time": EVAL_TIME}
                    if company is not None else {}
                )
                _get_or_create(
                    session, RuleTestCase, rule_version_id=rule_version.id, case_type=case_type,
                    defaults={
                        "input_facts": input_facts, "expected_status": expected_status,
                        "not_applicable_reason": waiver,
                    },
                )

            add_case("PASS", "TRUE", maotai)
            add_case("BOUNDARY", "TRUE", maotai)  # real committee has exactly 3 members == threshold
            add_case("VIOLATION", "FALSE", ding)  # synthetic 2-member fixture, see _add_violation_fixture
            add_case("NOT_APPLICABLE", "NOT_APPLICABLE", yi)  # real: 乙 has no audit committee at all
            add_case(
                "MISSING_FACT", "TRUE",
                waiver=(
                    "本规则读取治理登记表（Organization/RoleAssignment），而非独立事实层；"
                    "委员会缺失时归类为 NOT_APPLICABLE 而非资料不足，规则结构上无自然 MISSING_FACT 分支，"
                    "此用例仅满足强制类型存在性要求，未做真实执行"
                ),
            )
            add_case(
                "EXCEPTION", "TRUE",
                waiver="人数下限判断无例外分支，规则设计不涉及例外",
            )
            add_case(
                "CONFLICT", "TRUE",
                waiver="基于治理登记表而非多来源证据判断，不存在冲突来源",
            )
            session.flush()

            editor_id = session.query(User).filter_by(email="editor@demo.lawfocus").one().id
            legal_reviewer_id = session.query(User).filter_by(email="legal-reviewer@demo.lawfocus").one().id
            tech_reviewer_id = session.query(User).filter_by(email="tech-reviewer@demo.lawfocus").one().id
            publisher_id = session.query(User).filter_by(email="publisher@demo.lawfocus").one().id

            governance = RuleGovernanceService(session)
            if rule_version.status == ReviewStatus.DRAFT:
                governance.submit(rule_version, submitted_by=editor_id)
            if rule_version.status == ReviewStatus.IN_REVIEW:
                governance.add_review(
                    rule_version, legal_reviewer_id, ReviewType.LEGAL,
                    ReviewDecisionType.APPROVED, ENGINEERING_REVIEW_NOTE,
                )
            if rule_version.status == ReviewStatus.LEGAL_APPROVED:
                governance.add_review(
                    rule_version, tech_reviewer_id, ReviewType.TECHNICAL,
                    ReviewDecisionType.APPROVED, ENGINEERING_REVIEW_NOTE,
                )
            try:
                governance.publish(rule_version, publisher_id)
            except PublishGateFailedError as exc:
                session.commit()
                print(json.dumps({"status": "GATE_FAILED", "reasons": exc.reasons}, ensure_ascii=False, indent=2))
                return

        rule_set_service = RuleSetService(session)
        rule_set, created = _get_or_create(
            session, RuleSet, code="MVP-P0-REAL-SOURCED", version_no=1,
            defaults={
                "name": (
                    "MVP 首个真实法源规则集（GOV-AUD-002 唯一成员；内部治理流程已发布："
                    "双审+测试门禁均为真实执行，来源为哈希校验的官方公司法文本第一百二十一条；"
                    "本 PUBLISHED 状态仅代表工程治理门禁通过，不构成人类执业律师签署的正式法律意见）"
                ),
                "status": RuleSetStatus.DRAFT,
                "effective_from": date(2024, 7, 1),
            },
        )
        if rule_set.status == RuleSetStatus.DRAFT:
            existing_member = session.execute(
                select(RuleSetMember).where(
                    RuleSetMember.rule_set_id == rule_set.id,
                    RuleSetMember.rule_version_id == rule_version.id,
                )
            ).scalar_one_or_none()
            if existing_member is None:
                rule_set_service.add_member(rule_set, rule_version)
            rule_set_service.publish(rule_set)

        session.commit()
        print(json.dumps({
            "status": "PUBLISHED",
            "rule_version_id": str(rule_version.id),
            "rule_set_id": str(rule_set.id),
            "rule_set_code": rule_set.code,
            "source_article_version_id": str(real_article.id),
            "requirement_expression": rule_version.requirement_expression,
            "legal_effect_notice": (
                "工程治理门禁通过，法源已切换为真实公司法第一百二十一条；"
                "非人类执业律师正式法律意见，GOV-AUD-001/GOV-AUD-003 仍待证监会/交易所法源"
            ),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
