import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

settings = get_settings()

app = FastAPI(
    title="经济法知识图谱与上市公司治理合规推理系统 API",
    version="0.1.0",
)

register_exception_handlers(app)


@app.middleware("http")
async def assign_trace_id(request: Request, call_next):
    request.state.trace_id = str(uuid.uuid4())
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


app.include_router(api_router, prefix="/api/v1")
