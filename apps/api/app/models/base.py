import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def valid_interval_check(start_col: str = "valid_from", end_col: str = "valid_to") -> CheckConstraint:
    """CHECK that `end_col` is null or strictly after `start_col` — enforces the
    half-open [valid_from, valid_to) invariant at the database layer too, not just
    in app.domain.time_interval.
    """
    return CheckConstraint(
        f"{end_col} IS NULL OR {end_col} > {start_col}", name=f"ck_{start_col}_{end_col}_interval"
    )
