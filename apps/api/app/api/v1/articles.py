import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import CurrentUser, DbSession
from app.schemas.synthesis import RuleSynthesisOut, SynthesisOut, TextSegmentOut
from app.services.synthesis_service import ArticleVersionNotFoundError, SynthesisService

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/{article_version_id}/synthesis", response_model=SynthesisOut)
def get_article_synthesis(
    article_version_id: uuid.UUID, db: DbSession, _user: CurrentUser
) -> SynthesisOut:
    try:
        result = SynthesisService(db).get_synthesis(article_version_id)
    except ArticleVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTICLE_VERSION_NOT_FOUND", "message": str(exc)},
        ) from exc

    return SynthesisOut(
        article_version_id=article_version_id,
        generated_by=result.generated_by,
        text_segments=[
            TextSegmentOut(text=s.text, concept_id=uuid.UUID(s.concept_id) if s.concept_id else None)
            for s in result.segments
        ],
    )


@router.get("/{article_version_id}/rule-synthesis", response_model=RuleSynthesisOut)
def get_article_rule_synthesis(
    article_version_id: uuid.UUID, db: DbSession, _user: CurrentUser
) -> RuleSynthesisOut:
    try:
        result = SynthesisService(db).get_rule_synthesis(article_version_id)
    except ArticleVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTICLE_VERSION_NOT_FOUND", "message": str(exc)},
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RULE_SYNTHESIS_NOT_AVAILABLE",
                "message": "no PUBLISHED rule with a renderable requirement is bound to this article",
            },
        )

    return RuleSynthesisOut(
        article_version_id=article_version_id,
        rule_id=uuid.UUID(result.rule_id),
        rule_code=result.rule_code,
        rule_name=result.rule_name,
        text_segments=[
            TextSegmentOut(text=s.text, concept_id=uuid.UUID(s.concept_id) if s.concept_id else None)
            for s in result.segments
        ],
    )
