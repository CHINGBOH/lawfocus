"""Run the MVP-P0-REAL-SOURCED rule set (GOV-AUD-002 bound to real Company Law
Art. 121) against the real, hash-verified 贵州茅台 (600519) sample.

This is the "重新运行 600519 样本" step from 09-当前完成度评估与剩余工作指南.md §5,
scoped to the single rule that was honestly promoted this round (see
scripts/promote_gov_aud_002.py's module docstring for why GOV-AUD-001/003 are
excluded). The printed notice is deliberately explicit that this still is not
a certified legal opinion.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Conclusion, LegalRule, LegalRuleVersion, LegalSubject, RuleSet, Tenant
from app.services.rule_engine import RuleEngine


def main() -> None:
    with SessionLocal() as session:
        tenant = session.execute(select(Tenant).where(Tenant.code == "demo-tenant")).scalar_one()
        company = session.execute(select(LegalSubject).where(
            LegalSubject.name == "贵州茅台酒股份有限公司",
            LegalSubject.exchange == "SSE:600519",
        )).scalar_one()
        rule_set = session.execute(select(RuleSet).where(
            RuleSet.code == "MVP-P0-REAL-SOURCED", RuleSet.version_no == 1
        )).scalar_one()
        check = RuleEngine(session).run_compliance_check(
            tenant_id=tenant.id,
            company_id=company.id,
            evaluation_time=datetime(2026, 1, 1, tzinfo=UTC),
            rule_set_id=rule_set.id,
            idempotency_key="real-sourced-sample-600519-2026-v1",
            requested_by=None,
        )
        session.commit()
        rows = session.execute(
            select(LegalRule.code, Conclusion.result_status, Conclusion.missing_facts)
            .join(LegalRuleVersion, Conclusion.rule_version_id == LegalRuleVersion.id)
            .join(LegalRule, LegalRuleVersion.rule_id == LegalRule.id)
            .where(Conclusion.compliance_check_id == check.id)
            .order_by(LegalRule.code)
        ).all()
        print(json.dumps({
            "check_id": str(check.id),
            "company": company.name,
            "evaluation_date": "2026-01-01",
            "rule_set": "MVP-P0-REAL-SOURCED/v1",
            "legal_effect_notice": (
                "GOV-AUD-002 引用真实公司法第一百二十一条（人数下限≥3），已通过工程双审+测试门禁；"
                "非人类执业律师签署的正式法律意见；GOV-AUD-001/003 尚未真实法源化，不在本规则集内"
            ),
            "results": [
                {"rule_code": code, "status": status.value, "missing_facts": missing}
                for code, status, missing in rows
            ],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
