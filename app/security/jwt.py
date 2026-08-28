from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

settings = get_settings()


class TokenError(Exception):
    pass


def create_access_token(*, user_id: str, organization_id: str, role: str) -> tuple[str, int]:
    """Issues a signed JWT carrying the tenant claim.

    `organization_id` is embedded here, at login time, from the authenticated
    user's own row — the ONLY place it is ever derived from anything but a
    verified signature thereafter (see docs/ADR.md ADR-2). It cannot be
    supplied or altered by a later request.
    """
    now = datetime.now(UTC)
    expires_in = settings.jwt_expire_minutes * 60
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": organization_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
