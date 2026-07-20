"""Run the published MVP demo rule set against the imported real-company sample."""

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
            RuleSet.code == "MVP-P0-DEMO", RuleSet.version_no == 1
        )).scalar_one()
        check = RuleEngine(session).run_compliance_check(
            tenant_id=tenant.id,
            company_id=company.id,
            evaluation_time=datetime(2025, 12, 31, tzinfo=UTC),
            rule_set_id=rule_set.id,
            idempotency_key="official-sample-600519-2025-v1",
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
            "evaluation_date": "2025-12-31",
            "rule_set": "MVP-P0-DEMO/v1",
            "legal_effect_notice": "规则集法源仍为DEMO/UNVERIFIED，仅验证真实数据链路，不构成法律意见",
            "results": [
                {"rule_code": code, "status": status.value, "missing_facts": missing}
                for code, status, missing in rows
            ],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
