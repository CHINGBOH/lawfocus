import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import CreatedAtMixin, UUIDPk
from app.models.enums import RbacRoleCode


class Tenant(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "tenant"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base, UUIDPk, CreatedAtMixin):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    role_grants: Mapped[list["UserRole"]] = relationship(back_populates="user")


class Role(Base, UUIDPk):
    __tablename__ = "role"

    code: Mapped[RbacRoleCode] = mapped_column(
        Enum(RbacRoleCode, name="rbac_role_code"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class UserRole(Base, UUIDPk, CreatedAtMixin):
    """A role grant, optionally scoped to a tenant.

    tenant_id NULL means a global grant (e.g. Reader, Auditor, SystemAdmin);
    non-null scopes the grant to one tenant (e.g. ComplianceUser for tenant X).
    """

    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "tenant_id", name="uq_user_role_scope"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="role_grants")
    role: Mapped[Role] = relationship()
    tenant: Mapped[Tenant | None] = relationship()
