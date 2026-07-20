from fastapi import APIRouter

from app.api.v1.articles import router as articles_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.concepts import router as concepts_router
from app.api.v1.facts import router as facts_router
from app.api.v1.laws import router as laws_router
from app.api.v1.rules import router as rules_router
from app.api.v1.rulesets import router as rulesets_router
from app.api.v1.subjects import router as subjects_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(laws_router)
api_router.include_router(articles_router)
api_router.include_router(concepts_router)
api_router.include_router(facts_router)
api_router.include_router(compliance_router)
api_router.include_router(rules_router)
api_router.include_router(rulesets_router)
api_router.include_router(subjects_router)
