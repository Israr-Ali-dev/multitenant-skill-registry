from pydantic import BaseModel


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    request_id: str | None = None
    errors: list[dict] | None = None
