import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import CurrentUser, DbSession
from app.schemas.concept import ConceptDetailOut, ConceptPreviewOut, ConceptSourceOut
from app.schemas.legal import ArticleVersionOut
from app.services.concept_service import ConceptNotFoundError, ConceptService

router = APIRouter(prefix="/concepts", tags=["concepts"])

_SHORT_DEFINITION_LENGTH = 40


@router.get("/{concept_id}", response_model=ConceptDetailOut)
def get_concept(
    concept_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
    at: date | None = None,
) -> ConceptDetailOut:
    try:
        detail = ConceptService(db).get_concept_detail(concept_id, at or date.today())
    except ConceptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONCEPT_NOT_FOUND", "message": str(exc)},
        ) from exc

    return ConceptDetailOut(
        id=detail.concept.id,
        code=detail.concept.code,
        name=detail.concept.name,
        concept_type=detail.concept.concept_type,
        status=detail.concept.status,
        definition=detail.active_version.definition,
        review_status=detail.active_version.review_status,
        valid_from=detail.active_version.valid_from,
        valid_to=detail.active_version.valid_to,
        sources=[
            ConceptSourceOut(article_version=ArticleVersionOut.model_validate(av))
            for av in detail.source_article_versions
        ],
    )


@router.get("/{concept_id}/preview", response_model=ConceptPreviewOut)
def get_concept_preview(concept_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> ConceptPreviewOut:
    try:
        detail = ConceptService(db).get_concept_detail(concept_id, date.today())
    except ConceptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONCEPT_NOT_FOUND", "message": str(exc)},
        ) from exc

    definition = detail.active_version.definition
    if len(definition) <= _SHORT_DEFINITION_LENGTH:
        short = definition
    else:
        short = definition[:_SHORT_DEFINITION_LENGTH] + "…"
    return ConceptPreviewOut(
        id=detail.concept.id,
        code=detail.concept.code,
        name=detail.concept.name,
        concept_type=detail.concept.concept_type,
        review_status=detail.active_version.review_status,
        short_definition=short,
    )
