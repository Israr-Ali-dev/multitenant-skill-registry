from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(..., examples=["abc-construction"])
    email: str = Field(..., examples=["owner@abc-construction.test"])
    password: str = Field(..., min_length=1, examples=["OwnerPass123!"])


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
