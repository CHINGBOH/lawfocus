import uuid
from datetime import date

from fastapi import HTTPException, status
from fastapi.routing import APIRouter

from app.api.v1.deps import CurrentUser, DbSession
from app.models.enums import SubjectType
from app.schemas.pagination import Page, paginate_params
from app.schemas.subject import OrganizationGovernanceOut, SubjectGovernanceOut, SubjectOut
from app.services.subject_service import SubjectNotFoundError, SubjectService

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("", response_model=Page[SubjectOut])
def list_subjects(
    db: DbSession,
    _user: CurrentUser,
    subject_type: SubjectType | None = None,
    listed: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Page[SubjectOut]:
    page, page_size = paginate_params(page, page_size)
    items, total = SubjectService(db).list_subjects(
        subject_type=subject_type, listed=listed, page=page, page_size=page_size
    )
    return Page(items=items, page=page, page_size=page_size, total=total)  # type: ignore[arg-type]


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> SubjectOut:
    try:
        return SubjectService(db).get_subject(subject_id)  # type: ignore[return-value]
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBJECT_NOT_FOUND", "message": str(exc)},
        ) from exc


@router.get("/{subject_id}/governance", response_model=SubjectGovernanceOut)
def get_subject_governance(
    subject_id: uuid.UUID, db: DbSession, _user: CurrentUser, at: date | None = None
) -> SubjectGovernanceOut:
    try:
        snapshot = SubjectService(db).get_governance(subject_id, at or date.today())
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBJECT_NOT_FOUND", "message": str(exc)},
        ) from exc

    return SubjectGovernanceOut(
        subject=snapshot["subject"],
        at=snapshot["at"],
        organizations=[
            OrganizationGovernanceOut(organization=o["organization"], members=o["members"])
            for o in snapshot["organizations"]
        ],
    )
