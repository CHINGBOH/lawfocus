import uuid

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleGrantOut(BaseModel):
    role_code: str
    tenant_id: uuid.UUID | None


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    grants: list[RoleGrantOut]
