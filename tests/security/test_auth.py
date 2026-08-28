"""Authentication edge cases: forged/tampered tokens, wrong org/password,
inactive users. All map to 401 (see docs/ADR.md — auth failures are 401,
in-tenant permission failures are 403, cross-tenant existence is 404)."""

import jwt

from app.core.config import get_settings
from tests.conftest import auth_headers, login

settings = get_settings()


async def test_login_wrong_password_rejected(client, two_orgs):
    org_a, _ = two_orgs
    resp = await client.post(
        "/auth/login",
        json={
            "organization_slug": org_a.org.slug,
            "email": org_a.email("owner"),
            "password": "definitely-wrong",
        },
    )
    assert resp.status_code == 401


async def test_login_wrong_organization_slug_rejected(client, two_orgs):
    org_a, _ = two_orgs
    resp = await client.post(
        "/auth/login",
        json={
            "organization_slug": "does-not-exist",
            "email": org_a.email("owner"),
            "password": "TestFixturePass123!",
        },
    )
    assert resp.status_code == 401


async def test_login_user_from_other_org_with_right_password_rejected(client, two_orgs):
    """A user that exists (with a valid password) but under a different
    organization slug than the one supplied must not authenticate — proves
    org selection isn't just cosmetic."""
    org_a, org_b = two_orgs
    resp = await client.post(
        "/auth/login",
        json={
            "organization_slug": org_b.org.slug,
            "email": org_a.email("owner"),  # belongs to org A, not org B
            "password": "TestFixturePass123!",
        },
    )
    assert resp.status_code == 401


async def test_missing_authorization_header_rejected(client, two_orgs):
    org_a, _ = two_orgs
    resp = await client.get("/skills")
    assert resp.status_code == 401


async def test_malformed_authorization_header_rejected(client, two_orgs):
    resp = await client.get("/skills", headers={"Authorization": "NotBearer abc"})
    assert resp.status_code == 401


async def test_token_signed_with_wrong_secret_rejected(client, two_orgs):
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    forged = jwt.encode(claims, "an-attacker-controlled-secret", algorithm=settings.jwt_algorithm)

    resp = await client.get("/skills", headers=auth_headers(forged))
    assert resp.status_code == 401


async def test_token_with_swapped_org_id_claim_rejected(client, two_orgs):
    """A token whose org_id claim is tampered with (then re-signed with the
    same secret an attacker does not actually have) must still fail — this
    simulates the secret being known, worst case, and shows the user lookup
    (existence + role match in that exact org) is a second independent gate.
    """
    org_a, org_b = two_orgs
    token = await login(client, org_a, "owner")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    claims["org_id"] = str(org_b.org.id)
    forged = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    resp = await client.get("/skills", headers=auth_headers(forged))
    # The user id in `sub` does not exist under org_b, so lookup fails closed.
    assert resp.status_code == 401


async def test_expired_token_rejected(client, two_orgs):
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    claims["exp"] = 0  # already expired
    expired = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    resp = await client.get("/skills", headers=auth_headers(expired))
    assert resp.status_code == 401
