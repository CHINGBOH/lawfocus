from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str
    details: dict | None = None
