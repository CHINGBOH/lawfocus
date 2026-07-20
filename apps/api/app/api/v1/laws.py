import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Request, status

from app.api.v1.deps import CurrentUser, DbSession, get_trace_id
from app.schemas.legal import (
    ArticleNavigationOut,
    ArticleSummaryOut,
    ArticleVersionOut,
    LawOut,
    LegalVersionOut,
)
from app.services.audit_service import AuditService
from app.services.legal_repository_service import (
    ArticleNotFoundError,
    LawNotFoundError,
    LegalRepositoryService,
)

router = APIRouter(tags=["laws"])

_SUMMARY_LENGTH = 60


def _summarize(article_text: str) -> str:
    stripped = article_text.strip()
    return stripped if len(stripped) <= _SUMMARY_LENGTH else stripped[:_SUMMARY_LENGTH] + "…"


@router.get("/laws", response_model=list[LawOut])
def list_laws(db: DbSession, _user: CurrentUser) -> list[LawOut]:
    return LegalRepositoryService(db).list_laws()  # type: ignore[return-value]


@router.get("/laws/{law_code}/versions", response_model=list[LegalVersionOut])
def list_law_versions(law_code: str, db: DbSession, _user: CurrentUser) -> list[LegalVersionOut]:
    try:
        return LegalRepositoryService(db).list_versions_for_document(law_code)  # type: ignore[return-value]
    except LawNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "LAW_NOT_FOUND", "message": str(exc)},
        ) from exc


@router.get(
    "/laws/{law_code}/versions/{version_name}/articles",
    response_model=list[ArticleSummaryOut],
)
def list_law_version_articles(
    law_code: str, version_name: str, db: DbSession, _user: CurrentUser
) -> list[ArticleSummaryOut]:
    try:
        directory = LegalRepositoryService(db).list_article_directory(law_code, version_name)
    except LawNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "LAW_NOT_FOUND", "message": str(exc)},
        ) from exc
    return [
        ArticleSummaryOut(
            article_no=av.article_no,
            chapter_no=av.chapter_no,
            section_no=av.section_no,
            summary=_summarize(av.article_text),
        )
        for av in directory
    ]


def _record_view(request: Request, db: DbSession, user: CurrentUser, article_version_id: uuid.UUID) -> None:
    AuditService(db).record(
        trace_id=get_trace_id(request),
        actor_id=user.id,
        action="VIEW",
        resource_type="article_version",
        resource_id=str(article_version_id),
        decision="ALLOWED",
    )
    db.commit()


@router.get(
    "/laws/{law_code}/versions/{version_name}/articles/{article_no}",
    response_model=ArticleVersionOut,
)
def get_article_version(
    law_code: str,
    version_name: str,
    article_no: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> ArticleVersionOut:
    try:
        article_version = LegalRepositoryService(db).get_article_version_by_version_name(
            law_code, version_name, article_no
        )
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTICLE_NOT_FOUND", "message": str(exc)},
        ) from exc
    _record_view(request, db, user, article_version.id)
    return article_version  # type: ignore[return-value]


@router.get(
    "/laws/{law_code}/versions/{version_name}/articles/{article_no}/navigation",
    response_model=ArticleNavigationOut,
)
def get_article_navigation(
    law_code: str,
    version_name: str,
    article_no: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> ArticleNavigationOut:
    try:
        current, previous_no, next_no = LegalRepositoryService(db).get_article_navigation(
            law_code, version_name, article_no
        )
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTICLE_NOT_FOUND", "message": str(exc)},
        ) from exc
    _record_view(request, db, user, current.id)
    return ArticleNavigationOut(
        current=ArticleVersionOut.model_validate(current),
        previous_article_no=previous_no,
        next_article_no=next_no,
    )


@router.get(
    "/laws/{law_code}/articles/{article_no}/effective",
    response_model=ArticleVersionOut,
)
def get_effective_article_version(
    law_code: str,
    article_no: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    at: date | None = None,
) -> ArticleVersionOut:
    """Convenience 'as-of-date' lookup — defaults to today, matching the
    reading loop's default of showing the currently-effective text."""
    try:
        article_version = LegalRepositoryService(db).get_effective_article_version(
            law_code, article_no, at or date.today()
        )
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTICLE_NOT_FOUND", "message": str(exc)},
        ) from exc
    _record_view(request, db, user, article_version.id)
    return article_version  # type: ignore[return-value]
