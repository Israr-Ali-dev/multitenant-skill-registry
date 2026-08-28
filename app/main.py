from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestIDMiddleware

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="Jarvis AI COO — Organization-Scoped Skill Registry",
    description=(
        "Vertical slice: multi-tenant skill drafting, review, immutable "
        "versioning, and owner-gated activation with tenant isolation and audit."
    ),
    version="0.1.0",
)

app.add_middleware(RequestIDMiddleware)
register_exception_handlers(app)

app.include_router(v1_router, prefix="/api/v1")
