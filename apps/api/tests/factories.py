import uuid

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Role, Tenant, User, UserRole
from app.models.enums import RbacRoleCode


def make_tenant(db_session: Session, code: str | None = None) -> Tenant:
    tenant = Tenant(code=code or f"tenant-{uuid.uuid4().hex[:8]}", name="测试租户")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def make_user_with_role(
    db_session: Session,
    role_code: RbacRoleCode,
    *,
    tenant: Tenant | None = None,
    password: str = "TestPass123!",
    email: str | None = None,
) -> User:
    user = User(
        email=email or f"{uuid.uuid4().hex[:8]}@test.lawfocus",
        hashed_password=hash_password(password),
        display_name="测试用户",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter_by(code=role_code).one_or_none()
    if role is None:
        role = Role(code=role_code, name=role_code.value)
        db_session.add(role)
        db_session.flush()

    db_session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=tenant.id if tenant else None))
    db_session.flush()
    return user


# Business thresholds for the parameterized P0 rules (07 指南 R1): handlers read
# these from LegalRuleVersion.requirement_expression, never from code defaults.
# Mirrors scripts/seed_demo.py so fixtures exercise the same parameters as the demo.
DEMO_REQUIREMENT_EXPRESSIONS: dict[str, dict] = {
    "GOV-ID-001": {"operator": "gte", "value": 2, "unit": "person"},
    "GOV-ID-002": {"operator": "gte_ratio", "numerator": 1, "denominator": 3},
    "GOV-AUD-002": {"operator": "gte", "value": 3, "unit": "person"},
    "GOV-AUD-003": {"operator": "gt_ratio", "numerator": 1, "denominator": 2},
}


def demo_requirement_expression(rule_code: str) -> dict:
    """Requirement expression a fixture rule version should carry: the real
    parameters for threshold/ratio rules, {} for rules without numeric params."""
    return dict(DEMO_REQUIREMENT_EXPRESSIONS.get(rule_code, {}))
