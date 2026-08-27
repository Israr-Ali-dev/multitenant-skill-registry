from fastapi import APIRouter

from app.api.v1 import audit, auth, health, runtime, skills

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(skills.router, prefix="/skills", tags=["skills"])
router.include_router(runtime.router, prefix="/runtime", tags=["runtime"])
router.include_router(audit.router, prefix="/audit", tags=["audit"])
