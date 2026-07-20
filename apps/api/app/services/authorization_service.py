import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, UserRole
from app.models.enums import RbacRoleCode


@dataclass(frozen=True)
class RoleGrant:
    role_code: RbacRoleCode
    tenant_id: uuid.UUID | None  # None means a global grant


@dataclass(frozen=True)
class AuthContext:
    """Bundles the authenticated user id with their role grants so 403/audit
    paths downstream of `require_roles` can still attribute an actor."""

    user_id: uuid.UUID
    grants: list[RoleGrant]


class AuthorizationService:
    """RBAC + tenant-scope checks. A role grant with tenant_id=None is global
    (Reader/Auditor/SystemAdmin-style); a grant with tenant_id set only
    authorizes actions scoped to that one tenant."""

    def __init__(self, session: Session):
        self.session = session

    def get_role_grants(self, user_id: uuid.UUID) -> list[RoleGrant]:
        stmt = (
            select(Role.code, UserRole.tenant_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return [RoleGrant(role_code=code, tenant_id=tenant_id) for code, tenant_id in self.session.execute(stmt)]

    def has_role(
        self,
        grants: list[RoleGrant],
        required: set[RbacRoleCode],
        tenant_id: uuid.UUID | None = None,
    ) -> bool:
        for grant in grants:
            if grant.role_code not in required:
                continue
            if grant.tenant_id is None:
                return True  # global grant authorizes any tenant
            if tenant_id is not None and grant.tenant_id == tenant_id:
                return True
        return False

    def accessible_tenant_ids(self, grants: list[RoleGrant]) -> set[uuid.UUID] | None:
        """None means 'every tenant' (holder has at least one global grant)."""
        if any(grant.tenant_id is None for grant in grants):
            return None
        return {grant.tenant_id for grant in grants if grant.tenant_id is not None}
