from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, MeOut, RoleGrantOut, TokenResponse
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "email or password is incorrect"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeOut)
def get_me(user: CurrentUser, db: DbSession) -> MeOut:
    """So the frontend never has to ask a human to type a tenant/user UUID —
    it fetches this once after login and uses `grants` to know which
    tenant(s) the session can act in."""
    grants = AuthorizationService(db).get_role_grants(user.id)
    return MeOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        grants=[RoleGrantOut(role_code=g.role_code, tenant_id=g.tenant_id) for g in grants],
    )
