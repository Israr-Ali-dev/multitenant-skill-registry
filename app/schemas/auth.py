from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(..., examples=["abc-construction"])
    email: str = Field(..., examples=["owner@abc-construction.test"])
    # Matches the password `scripts/seed_fixtures.py` sets for every seeded
    # fixture user, so Swagger UI's example is a working credential out of
    # the box instead of a placeholder you have to overwrite each time.
    password: str = Field(..., min_length=1, examples=["FixtureDemoPass123!"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PrincipalOut(BaseModel):
    user_id: str
    organization_id: str
    organization_name: str
    role: str
    email: str
