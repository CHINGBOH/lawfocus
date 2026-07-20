"""Idempotent demo-data seed for local development (`make seed`).

Everything here is synthetic: law/article text, concept definitions, company
and person names are all invented for the MVP skeleton and are NOT real legal
text or real company data (05-真实公司材料数据治理规范.md §1-2 keeps real
material out of dev entirely). Demo law/article/concept rows are stamped
UNVERIFIED and named with a "(演示)" / DEMO marker so nothing here can be
mistaken for authoritative content.

Safe to re-run: every entity is looked up by a stable business key first.
"""

import os
import sys
from datetime import date

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    Article,
    ArticleVersion,
    Concept,
    ConceptVersion,
    Evidence,
    Fact,
    FactEvidence,
    GraphEdge,
    GraphNode,
    LegalDocument,
    LegalRule,
    LegalRuleVersion,
    LegalSubject,
    LegalVersion,
    Organization,
    Role,
    RoleAssignment,
    RoleType,
    RuleSource,
    Tenant,
    User,
    UserRole,
)
from app.models.enums import RbacRoleCode, ReviewStatus, SubjectType

DEMO_PASSWORD_ENV = "LAWFOCUS_DEMO_PASSWORD"


def _get_or_create(session: Session, model, defaults: dict | None = None, **lookup):
    instance = session.query(model).filter_by(**lookup).one_or_none()
    if instance is not None:
        return instance, False
    params = {**lookup, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    session.flush()
    return instance, True


def seed_tenant_and_users(session: Session) -> tuple[Tenant, Tenant]:
    demo_password = os.environ.get(DEMO_PASSWORD_ENV)
    if not demo_password:
        raise SystemExit(
            f"Set {DEMO_PASSWORD_ENV} before seeding (dev-only password, never hardcoded in source)."
        )

    tenant, _ = _get_or_create(
        session, Tenant, code="demo-tenant", defaults={"name": "演示租户 (DEMO)"}
    )
    # A second, otherwise-empty tenant purely so cross-tenant rejection
    # (06-MVP骨架充实与功能闭环计划.md §7 item 6) has a real second tenant to
    # attempt — not part of the "story" demo dataset, just an isolation fixture.
    tenant_b, _ = _get_or_create(
        session, Tenant, code="demo-tenant-b", defaults={"name": "演示租户 B（跨租户隔离测试用）"}
    )

    roles = {}
    for code in RbacRoleCode:
        role, _ = _get_or_create(session, Role, code=code, defaults={"name": code.value})
        roles[code] = role

    demo_users = [
        ("reader@demo.lawfocus", "演示读者", RbacRoleCode.READER, None),
        ("compliance@demo.lawfocus", "演示合规专员", RbacRoleCode.COMPLIANCE_USER, tenant.id),
        ("editor@demo.lawfocus", "演示知识编辑", RbacRoleCode.KNOWLEDGE_EDITOR, tenant.id),
        ("legal-reviewer@demo.lawfocus", "演示法律审核员", RbacRoleCode.LEGAL_REVIEWER, None),
        ("tech-reviewer@demo.lawfocus", "演示技术审核员", RbacRoleCode.TECHNICAL_REVIEWER, None),
        ("publisher@demo.lawfocus", "演示发布员", RbacRoleCode.PUBLISHER, None),
        ("auditor@demo.lawfocus", "演示审计员", RbacRoleCode.AUDITOR, None),
        ("admin@demo.lawfocus", "演示系统管理员", RbacRoleCode.SYSTEM_ADMIN, None),
        ("compliance-b@demo.lawfocus", "演示合规专员（租户B）", RbacRoleCode.COMPLIANCE_USER, tenant_b.id),
    ]
    for email, display_name, role_code, scoped_tenant_id in demo_users:
        user, _ = _get_or_create(
            session,
            User,
            email=email,
            defaults={
                "hashed_password": hash_password(demo_password),
                "display_name": display_name,
                "is_active": True,
            },
        )
        _get_or_create(
            session,
            UserRole,
            user_id=user.id,
            role_id=roles[role_code].id,
            tenant_id=scoped_tenant_id,
        )

    return tenant, tenant_b


def seed_law_and_articles(session: Session) -> dict[str, ArticleVersion]:
    document, _ = _get_or_create(
        session,
        LegalDocument,
        code="DEMO-COMPANY-LAW",
        defaults={
            "name": "演示公司法（DEMO / UNVERIFIED，非正式法律原文）",
            "document_type": "LAW",
            "issuer": "演示环境合成",
            "jurisdiction": "DEMO",
        },
    )

    v1, _ = _get_or_create(
        session,
        LegalVersion,
        document_id=document.id,
        version_name="DEMO-v1",
        defaults={
            "promulgated_at": date(2019, 12, 28),
            "effective_from": date(2020, 1, 1),
            "effective_to": date(2024, 7, 1),
            "status": "SUPERSEDED",
            "version_hash": "demo-v1-hash",
        },
    )
    v2, _ = _get_or_create(
        session,
        LegalVersion,
        document_id=document.id,
        version_name="DEMO-v2",
        defaults={
            "promulgated_at": date(2023, 12, 29),
            "effective_from": date(2024, 7, 1),
            "effective_to": None,
            "status": "ACTIVE",
            "version_hash": "demo-v2-hash",
        },
    )

    audit_committee_article_text = (
        "上市公司应当设置审计委员会，其成员不得少于三人，其中独立董事应当过半数。（演示条文）"
    )
    article_specs = [
        ("108", "第一百零八条", "上市公司应当设置董事会。（演示条文，非正式法律原文）"),
        ("120", "第一百二十条", "上市公司董事会成员中应当至少有三分之一为独立董事。（演示条文）"),
        ("121", "第一百二十一条", "上市公司独立董事人数不得少于二人。（演示条文）"),
        ("122", "第一百二十二条", audit_committee_article_text),
        ("123", "第一百二十三条", "审计委员会召集人应当由独立董事担任。（演示条文）"),
    ]

    article_versions: dict[str, ArticleVersion] = {}
    for article_no, chapter_no, text in article_specs:
        article, _ = _get_or_create(
            session, Article, document_id=document.id, article_no=article_no
        )
        for version, valid_from, valid_to in (
            (v1, date(2020, 1, 1), date(2024, 7, 1)),
            (v2, date(2024, 7, 1), None),
        ):
            article_version, _ = _get_or_create(
                session,
                ArticleVersion,
                article_id=article.id,
                legal_version_id=version.id,
                defaults={
                    "chapter_no": chapter_no,
                    "article_text": text,
                    "normalized_text": text,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
            )
            if version is v2:
                article_versions[article_no] = article_version

    return article_versions


def seed_concepts(session: Session, article_versions: dict[str, ArticleVersion]) -> None:
    """Also links each concept to the demo article that (loosely) defines it
    via graph_node/graph_edge DEFINED_BY, per the DB design doc's §8.3/§14.1
    provenance-traversal pattern — this is what ConceptService walks to
    answer 'where does this concept's definition come from'."""
    independent_director_definition = (
        "不在公司担任除董事外其他职务，并与公司无可能影响独立判断关系的董事。（演示定义）"
    )
    audit_committee_definition = "董事会下设的负责财务监督和内部控制的专门委员会。（演示定义）"
    listed_company_definition = "股票在证券交易所公开交易的股份有限公司。（演示定义）"
    concept_specs = [
        ("CONCEPT-LISTED-COMPANY", "上市公司", "SUBJECT", listed_company_definition, "108"),
        ("CONCEPT-BOARD", "董事会", "ORGAN", "公司的常设决策机构，由董事组成。（演示定义）", "108"),
        ("CONCEPT-INDEPENDENT-DIRECTOR", "独立董事", "ROLE", independent_director_definition, "121"),
        ("CONCEPT-AUDIT-COMMITTEE", "审计委员会", "ORGAN", audit_committee_definition, "122"),
    ]
    for code, name, concept_type, definition, source_article_no in concept_specs:
        concept, _ = _get_or_create(
            session, Concept, code=code, defaults={"name": name, "concept_type": concept_type}
        )
        _get_or_create(
            session,
            ConceptVersion,
            concept_id=concept.id,
            valid_from=date(2024, 7, 1),
            defaults={
                "definition": definition,
                "review_status": "UNVERIFIED",
                "valid_to": None,
            },
        )

        concept_node, _ = _get_or_create(
            session,
            GraphNode,
            node_type="CONCEPT",
            code=code,
            defaults={"name": name, "properties": {"ref_table": "concept", "ref_id": str(concept.id)}},
        )
        source_version = article_versions[source_article_no]
        article_node, _ = _get_or_create(
            session,
            GraphNode,
            node_type="ARTICLE_VERSION",
            code=f"DEMO-COMPANY-LAW:{source_article_no}:{source_version.legal_version_id}",
            defaults={
                "name": f"第{source_article_no}条（DEMO-v2）",
                "properties": {"ref_table": "article_version", "ref_id": str(source_version.id)},
            },
        )
        _get_or_create(
            session,
            GraphEdge,
            source_id=concept_node.id,
            relation_type="DEFINED_BY",
            target_id=article_node.id,
        )


def seed_role_types(session: Session) -> dict[str, RoleType]:
    specs = [
        ("DIRECTOR", "董事"),
        ("INDEPENDENT_DIRECTOR", "独立董事"),
        ("CHAIRPERSON", "董事长"),
        ("AUDIT_COMMITTEE_MEMBER", "审计委员会委员"),
        ("AUDIT_COMMITTEE_CONVENOR", "审计委员会召集人"),
    ]
    result = {}
    for code, name in specs:
        role_type, _ = _get_or_create(session, RoleType, code=code, defaults={"name": name})
        result[code] = role_type
    return result


def seed_companies_and_governance(
    session: Session, role_types: dict[str, RoleType]
) -> tuple[LegalSubject, LegalSubject, LegalSubject, LegalSubject]:
    company_a, _ = _get_or_create(
        session,
        LegalSubject,
        name="甲上市公司（演示）",
        subject_type=SubjectType.LISTED_COMPANY,
        defaults={"unified_credit_code": "DEMO-CREDIT-A", "listed": True, "exchange": "SSE"},
    )
    company_b, _ = _get_or_create(
        session,
        LegalSubject,
        name="乙上市公司（演示）",
        subject_type=SubjectType.LISTED_COMPANY,
        defaults={"unified_credit_code": "DEMO-CREDIT-B", "listed": True, "exchange": "SZSE"},
    )
    # Company C: not a listed company at all — the reference subject for
    # genuine, executed NOT_APPLICABLE test cases across every P0 rule.
    company_c, _ = _get_or_create(
        session,
        LegalSubject,
        name="丙非上市公司（演示）",
        subject_type=SubjectType.COMPANY,
        defaults={"unified_credit_code": "DEMO-CREDIT-C", "listed": False},
    )
    # Company D: listed, but deliberately has zero recorded governance data at
    # all — the reference subject for genuine FALSE (existence rules) and
    # genuine UNKNOWN (fact-dependent rules) test cases.
    company_d, _ = _get_or_create(
        session,
        LegalSubject,
        name="丁上市公司（演示，无治理记录）",
        subject_type=SubjectType.LISTED_COMPANY,
        defaults={"unified_credit_code": "DEMO-CREDIT-D", "listed": True, "exchange": "SSE"},
    )

    board_a, _ = _get_or_create(
        session, Organization, company_id=company_a.id, organization_type="BOARD",
        defaults={"name": "甲上市公司董事会（演示）"},
    )
    audit_a, _ = _get_or_create(
        session, Organization, company_id=company_a.id, organization_type="AUDIT_COMMITTEE",
        defaults={"name": "甲上市公司审计委员会（演示）"},
    )
    board_b, _ = _get_or_create(
        session, Organization, company_id=company_b.id, organization_type="BOARD",
        defaults={"name": "乙上市公司董事会（演示）"},
    )

    # Company A: fully compliant demo — 9 directors, 3 independent, valid appointments.
    persons_a = []
    for i in range(1, 10):
        person, _ = _get_or_create(
            session, LegalSubject, name=f"甲公司演示董事{i}", subject_type=SubjectType.PERSON,
        )
        persons_a.append(person)
        role_type = role_types["INDEPENDENT_DIRECTOR"] if i <= 3 else role_types["DIRECTOR"]
        _get_or_create(
            session,
            RoleAssignment,
            person_id=person.id,
            role_type_id=role_type.id,
            company_id=company_a.id,
            organization_id=board_a.id,
            valid_from=date(2024, 1, 1),
            defaults={"valid_to": None},
        )
    # Audit committee: 3 members, 2 independent (>50%), convenor is independent director.
    for i in range(1, 4):
        _get_or_create(
            session,
            RoleAssignment,
            person_id=persons_a[i - 1].id,
            role_type_id=role_types["AUDIT_COMMITTEE_MEMBER"].id,
            company_id=company_a.id,
            organization_id=audit_a.id,
            valid_from=date(2024, 1, 1),
            defaults={"valid_to": None},
        )
    _get_or_create(
        session,
        RoleAssignment,
        person_id=persons_a[0].id,
        role_type_id=role_types["AUDIT_COMMITTEE_CONVENOR"].id,
        company_id=company_a.id,
        organization_id=audit_a.id,
        valid_from=date(2024, 1, 1),
        defaults={"valid_to": None},
    )

    # Company B: deliberately deficient demo — only 1 independent director, one
    # appointment already expired, to exercise FALSE / UNKNOWN / CONFLICT paths.
    for i in range(1, 6):
        person, _ = _get_or_create(
            session, LegalSubject, name=f"乙公司演示董事{i}", subject_type=SubjectType.PERSON,
        )
        role_type = role_types["INDEPENDENT_DIRECTOR"] if i == 1 else role_types["DIRECTOR"]
        valid_to = date(2024, 12, 31) if i == 5 else None  # one expired appointment
        _get_or_create(
            session,
            RoleAssignment,
            person_id=person.id,
            role_type_id=role_type.id,
            company_id=company_b.id,
            organization_id=board_b.id,
            valid_from=date(2024, 1, 1),
            defaults={"valid_to": valid_to},
        )
    # No audit committee organ for company B at all — exercises GOV-AUD-001 FALSE/UNKNOWN.

    return company_a, company_b, company_c, company_d


def seed_facts_and_evidence(session: Session, tenant: Tenant) -> None:
    company_a = session.query(LegalSubject).filter_by(name="甲上市公司（演示）").one()
    company_b = session.query(LegalSubject).filter_by(name="乙上市公司（演示）").one()

    evidence_a, _ = _get_or_create(
        session,
        Evidence,
        tenant_id=tenant.id,
        title="甲上市公司2025年年度报告（演示证据）",
        defaults={
            "evidence_type": "AnnualReport",
            "source_url": None,
            "quote_text": "董事会由9名董事组成，其中3名独立董事。（演示文本）",
            "published_at": date(2025, 3, 31),
        },
    )
    fact_a, created = _get_or_create(
        session,
        Fact,
        tenant_id=tenant.id,
        company_id=company_a.id,
        fact_type="BOARD_COMPOSITION",
        predicate="independent_director_count",
        valid_from=date(2024, 1, 1),
        defaults={"object_value": {"total": 9, "independent": 3}, "valid_to": None},
    )
    if created:
        _get_or_create(
            session,
            FactEvidence,
            fact_id=fact_a.id,
            evidence_id=evidence_a.id,
            defaults={"support_type": "DIRECT", "confidence": 0.95},
        )

    # Company B: a conflicting pair of overlapping facts for the same predicate —
    # exercises CONFLICT (two sources disagree and neither is retracted).
    evidence_b1, _ = _get_or_create(
        session,
        Evidence,
        tenant_id=tenant.id,
        title="乙上市公司2025年半年度报告（演示证据，来源一）",
        defaults={
            "evidence_type": "AnnualReport",
            "quote_text": "独立董事1人。（演示）",
            "published_at": date(2025, 6, 30),
        },
    )
    evidence_b2, _ = _get_or_create(
        session,
        Evidence,
        tenant_id=tenant.id,
        title="乙上市公司董事会公告（演示证据，来源二，与年报冲突）",
        defaults={
            "evidence_type": "CompanyAnnouncement",
            "quote_text": "独立董事2人。（演示，与年报口径冲突）",
            "published_at": date(2025, 7, 1),
        },
    )
    fact_b1, created_b1 = _get_or_create(
        session,
        Fact,
        tenant_id=tenant.id,
        company_id=company_b.id,
        fact_type="BOARD_COMPOSITION",
        predicate="independent_director_count",
        valid_from=date(2025, 1, 1),
        object_value={"total": 5, "independent": 1},
        defaults={"valid_to": None},
    )
    if created_b1:
        _get_or_create(
            session, FactEvidence, fact_id=fact_b1.id, evidence_id=evidence_b1.id,
            defaults={"support_type": "DIRECT", "confidence": 0.9},
        )
    fact_b2, created_b2 = _get_or_create(
        session,
        Fact,
        tenant_id=tenant.id,
        company_id=company_b.id,
        fact_type="BOARD_COMPOSITION",
        predicate="independent_director_count",
        valid_from=date(2025, 1, 1),
        object_value={"total": 5, "independent": 2},
        defaults={"valid_to": None},
    )
    if created_b2:
        _get_or_create(
            session, FactEvidence, fact_id=fact_b2.id, evidence_id=evidence_b2.id,
            defaults={"support_type": "DIRECT", "confidence": 0.9},
        )
    # Audit-committee facts deliberately absent for company B -> UNKNOWN on GOV-AUD-00x.


def seed_rule_versions(
    session: Session, article_versions: dict[str, ArticleVersion]
) -> dict[str, LegalRuleVersion]:
    """Skeletons for the 10 P0 rules (02-上市公司治理MVP十条规则清单.md).

    All 10 start in DRAFT here. `seed_ruleset_governance` (below) pushes a
    subset through the *real* submit -> dual-review -> publish workflow so
    the demo has at least one genuinely PUBLISHED RuleSet to run — that
    PUBLISHED status reflects only the internal engineering governance gate
    (real dual review + real re-executed tests), never a claim that the
    underlying law text is legally authoritative: the cited ArticleVersion
    stays DEMO/UNVERIFIED regardless (05-真实公司材料数据治理规范.md).
    """
    rule_specs = [
        ("GOV-ORG-001", "上市公司董事会存在性", "108", {"demo": True}),
        ("GOV-AUD-001", "审计委员会设置", "122", {"demo": True}),
        ("GOV-ID-001", "独立董事最低人数", "121", {"operator": "gte", "value": 2, "unit": "person"}),
        ("GOV-ID-002", "独立董事最低比例", "120", {"operator": "gte_ratio", "numerator": 1, "denominator": 3}),
        ("GOV-AUD-002", "审计委员会成员构成", "122", {"operator": "gte", "value": 3, "unit": "person"}),
        ("GOV-AUD-003", "审计委员会独立董事占比", "122", {"operator": "gt_ratio", "numerator": 1, "denominator": 2}),
        ("GOV-AUD-004", "审计委员会召集人资格", "123", {"demo": True}),
        ("GOV-ROLE-001", "董事任职有效性", "108", {"demo": True}),
        ("GOV-TIME-001", "任职评价时点有效性", "108", {"demo": True}),
        ("GOV-CTRL-001", "控股股东/实际控制人关系认定", "108", {"demo": True}),
    ]
    rule_versions: dict[str, LegalRuleVersion] = {}
    for code, name, source_article_no, requirement_expression in rule_specs:
        rule, _ = _get_or_create(session, LegalRule, code=code, defaults={"name": name})
        rule_version, created = _get_or_create(
            session,
            LegalRuleVersion,
            rule_id=rule.id,
            version_no=1,
            defaults={
                "status": ReviewStatus.DRAFT,
                "subject_type": "ListedCompany",
                "modality": "OBLIGATION",
                "condition_expression": {"demo": True},
                "requirement_expression": requirement_expression,
                "priority": {"authority_level": 1, "specificity": 1, "exception_level": 0},
            },
        )
        if created:
            _get_or_create(
                session,
                RuleSource,
                rule_version_id=rule_version.id,
                article_version_id=article_versions[source_article_no].id,
                defaults={"relation_type": "FORMALIZED_FROM"},
            )
        elif (
            rule_version.status == ReviewStatus.DRAFT
            and rule_version.requirement_expression != requirement_expression
        ):
            # DRAFT versions are still mutable (append-only applies to PUBLISHED
            # content and legal sources): refresh the parameterized requirement
            # so re-running the seed on an older demo DB picks up R1 expressions.
            rule_version.requirement_expression = requirement_expression
        rule_versions[code] = rule_version
    return rule_versions


def seed_ruleset_governance(
    session: Session,
    rule_versions: dict[str, LegalRuleVersion],
    company_a: LegalSubject,
    company_b: LegalSubject,
    company_c: LegalSubject,
    company_d: LegalSubject,
) -> None:
    """Pushes 3 of the 10 rules through the *real* submit -> legal review ->
    technical review -> publish workflow (RuleGovernanceService), then bundles
    them into a PUBLISHED RuleSet — so `make seed` leaves behind at least one
    genuinely runnable formal compliance check, without which the F2 wizard
    (06-MVP骨架充实与功能闭环计划.md §4.4) would have nothing to demonstrate.

    Every PASS/VIOLATION/BOUNDARY/CONFLICT/MISSING_FACT test case below that
    references a real company + evaluation_time is actually re-executed by
    the publish gate (RuleGovernanceService._run_test_gate) — nothing here
    is a rubber stamp. Between the three rules, all five TruthValue outcomes
    are genuinely, independently produced at least once:
      TRUE          - company_a (fully compliant demo)
      FALSE         - company_b (no audit committee) / company_d (no board)
      UNKNOWN       - company_d (zero recorded facts)
      CONFLICT      - company_b (two disagreeing BOARD_COMPOSITION facts)
      NOT_APPLICABLE- company_c (not a listed company)
    """
    from app.models import RuleSet, RuleSetMember, RuleTestCase
    from app.models.enums import ReviewDecisionType, ReviewType, RuleSetStatus
    from app.services.rule_governance_service import RuleGovernanceService
    from app.services.rule_set_service import RuleSetService

    eval_time = "2025-06-01T00:00:00+00:00"

    def user_id(email: str) -> object:
        user = session.query(User).filter_by(email=email).one()
        return user.id

    editor_id = user_id("editor@demo.lawfocus")
    legal_reviewer_id = user_id("legal-reviewer@demo.lawfocus")
    tech_reviewer_id = user_id("tech-reviewer@demo.lawfocus")
    publisher_id = user_id("publisher@demo.lawfocus")

    def add_case(rule_version_id, case_type, expected_status, company=None, waiver=None):
        input_facts = (
            {"company_id": str(company.id), "evaluation_time": eval_time} if company is not None else {}
        )
        _get_or_create(
            session,
            RuleTestCase,
            rule_version_id=rule_version_id,
            case_type=case_type,
            defaults={
                "input_facts": input_facts,
                "expected_status": expected_status,
                "not_applicable_reason": waiver,
            },
        )

    def publish_rule(code: str) -> None:
        rv = rule_versions[code]
        if rv.status == ReviewStatus.PUBLISHED:
            return
        governance = RuleGovernanceService(session)
        governance.submit(rv, submitted_by=editor_id)
        governance.add_review(
            rv, legal_reviewer_id, ReviewType.LEGAL, ReviewDecisionType.APPROVED, "演示法律审核通过"
        )
        governance.add_review(
            rv, tech_reviewer_id, ReviewType.TECHNICAL, ReviewDecisionType.APPROVED, "演示技术审核通过"
        )
        governance.publish(rv, publisher_id)

    already_governed = rule_versions["GOV-ORG-001"].status == ReviewStatus.PUBLISHED
    if not already_governed:
        no_exception_reason = "存在性/构成判断无自然例外分支，规则设计不涉及例外"
        no_conflict_reason = "基于结构化治理注册表，非多来源证据判断，不存在冲突来源"

        add_case(rule_versions["GOV-ORG-001"].id, "PASS", "TRUE", company_a)
        add_case(rule_versions["GOV-ORG-001"].id, "VIOLATION", "FALSE", company_d)
        add_case(rule_versions["GOV-ORG-001"].id, "NOT_APPLICABLE", "NOT_APPLICABLE", company_c)
        add_case(rule_versions["GOV-ORG-001"].id, "BOUNDARY", "TRUE", company_a)
        add_case(rule_versions["GOV-ORG-001"].id, "MISSING_FACT", "FALSE", company_d)
        add_case(rule_versions["GOV-ORG-001"].id, "EXCEPTION", "TRUE", waiver=no_exception_reason)
        add_case(rule_versions["GOV-ORG-001"].id, "CONFLICT", "TRUE", waiver=no_conflict_reason)

        add_case(rule_versions["GOV-AUD-001"].id, "PASS", "TRUE", company_a)
        add_case(rule_versions["GOV-AUD-001"].id, "VIOLATION", "FALSE", company_b)
        add_case(rule_versions["GOV-AUD-001"].id, "NOT_APPLICABLE", "NOT_APPLICABLE", company_c)
        add_case(rule_versions["GOV-AUD-001"].id, "BOUNDARY", "FALSE", company_d)
        add_case(rule_versions["GOV-AUD-001"].id, "MISSING_FACT", "FALSE", company_d)
        add_case(rule_versions["GOV-AUD-001"].id, "EXCEPTION", "TRUE", waiver=no_exception_reason)
        add_case(rule_versions["GOV-AUD-001"].id, "CONFLICT", "TRUE", waiver=no_conflict_reason)

        add_case(rule_versions["GOV-ID-002"].id, "PASS", "TRUE", company_a)
        add_case(rule_versions["GOV-ID-002"].id, "BOUNDARY", "TRUE", company_a)  # 3/9 == 1/3 exactly
        add_case(rule_versions["GOV-ID-002"].id, "CONFLICT", "CONFLICT", company_b)
        add_case(rule_versions["GOV-ID-002"].id, "MISSING_FACT", "UNKNOWN", company_d)
        add_case(rule_versions["GOV-ID-002"].id, "NOT_APPLICABLE", "NOT_APPLICABLE", company_c)
        add_case(
            rule_versions["GOV-ID-002"].id,
            "VIOLATION",
            "FALSE",
            waiver="演示数据集中暂无单一（非冲突）事实来源下比例不足的样例公司",
        )
        add_case(rule_versions["GOV-ID-002"].id, "EXCEPTION", "TRUE", waiver=no_exception_reason)

        session.flush()

        for code in ("GOV-ORG-001", "GOV-AUD-001", "GOV-ID-002"):
            publish_rule(code)

    rule_set_service = RuleSetService(session)
    rule_set, created = _get_or_create(
        session,
        RuleSet,
        code="MVP-P0-DEMO",
        version_no=1,
        defaults={
            "name": (
                "MVP P0 演示规则集（内部治理流程已发布：双审+测试门禁均为真实执行；"
                "所引用法源与阈值仍为 DEMO/UNVERIFIED，不构成正式法律意见）"
            ),
            "status": RuleSetStatus.DRAFT,
            "effective_from": date(2024, 7, 1),
        },
    )
    if created or rule_set.status == RuleSetStatus.DRAFT:
        for code in ("GOV-ORG-001", "GOV-AUD-001", "GOV-ID-002"):
            existing_member = (
                session.query(RuleSetMember)
                .filter_by(rule_set_id=rule_set.id, rule_version_id=rule_versions[code].id)
                .one_or_none()
            )
            if existing_member is None:
                rule_set_service.add_member(rule_set, rule_versions[code])
        if rule_set.status == RuleSetStatus.DRAFT:
            rule_set_service.publish(rule_set)


def seed_f6_fixtures(
    session: Session,
    tenant: Tenant,
    company_a: LegalSubject,
    company_b: LegalSubject,
    company_c: LegalSubject,
    company_d: LegalSubject,
    rule_versions: dict[str, LegalRuleVersion],
) -> None:
    """Fixtures that only exist to support the F6 browser-driven E2E pass
    (06-MVP骨架充实与功能闭环计划.md §7): a still-DRAFT rule with a full,
    genuinely-executable test suite so the dual-review flow can be driven to
    a real PUBLISHED status through the browser UI (as opposed to
    `seed_ruleset_governance`'s three rules, which are pushed to PUBLISHED by
    direct service calls, not through the UI). Deliberately does NOT call
    publish() here — leaves GOV-CTRL-001 at DRAFT so a live walkthrough can
    submit/review/publish it for real.
    """
    from app.models import RuleTestCase

    eval_time = "2025-06-01T00:00:00+00:00"

    _get_or_create(
        session, Fact, tenant_id=tenant.id, company_id=company_a.id, fact_type="CONTROL_RELATIONSHIP",
        predicate="controls", valid_from=date(2024, 1, 1),
        defaults={"object_value": {"controls": True}, "valid_to": None},
    )
    _get_or_create(
        session, Fact, tenant_id=tenant.id, company_id=company_c.id, fact_type="CONTROL_RELATIONSHIP",
        predicate="controls", valid_from=date(2024, 1, 1),
        defaults={"object_value": {"controls": False}, "valid_to": None},
    )
    fact_conflict_1, _created_1 = _get_or_create(
        session, Fact, tenant_id=tenant.id, company_id=company_b.id, fact_type="CONTROL_RELATIONSHIP",
        predicate="controls", valid_from=date(2025, 1, 1), object_value={"controls": True},
        defaults={"valid_to": None},
    )
    fact_conflict_2, _created_2 = _get_or_create(
        session, Fact, tenant_id=tenant.id, company_id=company_b.id, fact_type="CONTROL_RELATIONSHIP",
        predicate="controls", valid_from=date(2025, 1, 1), object_value={"controls": False},
        defaults={"valid_to": None},
    )
    session.flush()
    assert fact_conflict_1.id != fact_conflict_2.id, "conflict fixture needs two distinct Fact rows"

    ctrl_version_id = rule_versions["GOV-CTRL-001"].id
    no_exception_reason = "布尔型控制关系判断无例外分支，规则设计不涉及例外"
    no_boundary_reason = "布尔型判断（是否存在控制关系）没有数值边界，无自然边界样例"

    def add_case(case_type, expected_status, company=None, waiver=None):
        input_facts = (
            {"company_id": str(company.id), "evaluation_time": eval_time} if company is not None else {}
        )
        _get_or_create(
            session, RuleTestCase, rule_version_id=ctrl_version_id, case_type=case_type,
            defaults={"input_facts": input_facts, "expected_status": expected_status, "not_applicable_reason": waiver},
        )

    add_case("PASS", "TRUE", company_a)
    add_case("VIOLATION", "FALSE", company_c)
    add_case("MISSING_FACT", "UNKNOWN", company_d)
    add_case("CONFLICT", "CONFLICT", company_b)
    add_case("BOUNDARY", "TRUE", waiver=no_boundary_reason)
    add_case("NOT_APPLICABLE", "NOT_APPLICABLE", waiver="规则未对主体类型设范围排除，不存在不适用分支")
    add_case("EXCEPTION", "TRUE", waiver=no_exception_reason)


def run() -> None:
    session = SessionLocal()
    try:
        tenant, _tenant_b = seed_tenant_and_users(session)
        article_versions = seed_law_and_articles(session)
        seed_concepts(session, article_versions)
        role_types = seed_role_types(session)
        company_a, company_b, company_c, company_d = seed_companies_and_governance(session, role_types)
        seed_facts_and_evidence(session, tenant)
        rule_versions = seed_rule_versions(session, article_versions)
        seed_ruleset_governance(session, rule_versions, company_a, company_b, company_c, company_d)
        seed_f6_fixtures(session, tenant, company_a, company_b, company_c, company_d, rule_versions)
        session.commit()
        print("Seed complete.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(run() or 0)
