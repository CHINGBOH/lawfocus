import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import InvalidTokenError, decode_access_token
from app.models import User
from app.models.enums import RbacRoleCode
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthContext, AuthorizationService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


def get_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or str(uuid.uuid4())


def get_current_user(request: Request, credentials: BearerCredentials, db: DbSession) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "missing bearer token"},
        )
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        AuditService(db).record(
            trace_id=get_trace_id(request),
            action="AUTHENTICATE",
            resource_type="api_request",
            decision="DENIED",
            reason_code="INVALID_TOKEN",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_INACTIVE", "message": "user not found or inactive"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_auth_context(user: CurrentUser, db: DbSession) -> AuthContext:
    grants = AuthorizationService(db).get_role_grants(user.id)
    return AuthContext(user_id=user.id, grants=grants)


def require_roles(*allowed: RbacRoleCode):
    """Dependency factory: `Depends(require_roles(RbacRoleCode.AUDITOR, ...))`.

    Only checks role membership, not tenant scope — endpoints that take a
    `tenant_id` must additionally call `require_tenant_access(tenant_id, ctx,
    db, request)` themselves so a tenant-scoped grant for tenant A can't
    reach tenant B's resources.
    """

    def _dependency(
        request: Request,
        db: DbSession,
        ctx: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if not any(grant.role_code in allowed for grant in ctx.grants):
            AuditService(db).record(
                trace_id=get_trace_id(request),
                actor_id=ctx.user_id,
                action="AUTHORIZE",
                resource_type="api_request",
                decision="DENIED",
                reason_code="INSUFFICIENT_ROLE",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "insufficient role"},
            )
        return ctx

    return _dependency


def require_tenant_access(
    tenant_id: uuid.UUID, ctx: AuthContext, db: Session, request: Request
) -> None:
    if any(grant.tenant_id is None or grant.tenant_id == tenant_id for grant in ctx.grants):
        return
    AuditService(db).record(
        trace_id=get_trace_id(request),
        actor_id=ctx.user_id,
        tenant_id=tenant_id,
        action="AUTHORIZE",
        resource_type="api_request",
        decision="DENIED",
        reason_code="TENANT_FORBIDDEN",
    )
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "TENANT_FORBIDDEN", "message": "no grant scoped to this tenant"},
    )
