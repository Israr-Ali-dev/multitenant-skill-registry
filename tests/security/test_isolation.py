"""Tenant isolation — mandatory items #2, #3, #4, plus extra isolation
evidence (body-injection attempt, and a parametrized cross-org sweep).

Every cross-tenant case below asserts 404, never 403 (see docs/ADR.md ADR-4):
the API must never confirm that a foreign-tenant resource exists.
"""

import pytest

from tests.conftest import auth_headers, create_draft_skill, login


async def test_cross_org_read_denied(client, two_orgs):
    """Mandatory #2: cross-organization read is denied."""
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")
    token_b = await login(client, org_b, "owner")

    skill = await create_draft_skill(client, token_a)

    resp = await client.get(f"/skills/{skill['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404
    assert skill["slug"] not in resp.text


async def test_cross_org_update_denied(client, two_orgs):
    """Mandatory #3: cross-organization update (new version) is denied."""
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")
    token_b = await login(client, org_b, "owner")

    skill = await create_draft_skill(client, token_a)

    resp = await client.post(
        f"/skills/{skill['id']}/versions",
        headers=auth_headers(token_b),
        json={"instructions": "hostile edit", "requested_tools": []},
    )
    assert resp.status_code == 404

    # Prove nothing was actually written: org A still only has version 1.
    detail = await client.get(f"/skills/{skill['id']}", headers=auth_headers(token_a))
    assert len(detail.json()["versions"]) == 1


async def test_non_owner_activation_denied(client, two_orgs):
    """Mandatory #4: non-owner activation is denied (admin and member both)."""
    org_a, _org_b = two_orgs
    owner_token = await login(client, org_a, "owner")
    admin_token = await login(client, org_a, "admin")
    member_token = await login(client, org_a, "member")

    skill = await create_draft_skill(client, owner_token)
    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(owner_token),
        json={"decision": "approve"},
    )

    for token in (admin_token, member_token):
        resp = await client.post(
            f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)
        )
        assert resp.status_code == 403

    still_draft = await client.get(f"/skills/{skill['id']}", headers=auth_headers(owner_token))
    assert still_draft.json()["status"] == "draft"


async def test_body_organization_id_is_ignored(client, two_orgs):
    """A client cannot address another tenant by stuffing an organization_id
    into the request body — it isn't even a field the schema accepts, so the
    resource always lands in the caller's own org (see ADR-2)."""
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")

    resp = await client.post(
        "/skills",
        headers=auth_headers(token_a),
        json={
            "slug": "injected-org-skill",
            "name": "Injection Attempt",
            "instructions": "test",
            "requested_tools": [],
            "organization_id": str(org_b.org.id),  # not a real field; must be ignored
        },
    )
    assert resp.status_code == 201
    skill = resp.json()

    # It must be visible to org A (the real, token-derived org)...
    as_a = await client.get(f"/skills/{skill['id']}", headers=auth_headers(token_a))
    assert as_a.status_code == 200

    # ...and invisible to org B.
    token_b = await login(client, org_b, "owner")
    as_b = await client.get(f"/skills/{skill['id']}", headers=auth_headers(token_b))
    assert as_b.status_code == 404


@pytest.mark.parametrize(
    "method,path_suffix,payload",
    [
        ("GET", "", None),
        ("POST", "/versions", {"instructions": "x", "requested_tools": []}),
        ("POST", "/versions/1/review", {"decision": "approve"}),
        ("POST", "/versions/1/activate", None),
        ("POST", "/disable", None),
    ],
)
async def test_cross_org_route_sweep_returns_404(
    client, two_orgs, method, path_suffix, payload
):
    """Fuzz-ish sweep: every skill-scoped route, called with a foreign skill id,
    returns 404 — never 403, never 200, never a validation error that leaks
    existence."""
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")
    token_b = await login(client, org_b, "owner")

    skill = await create_draft_skill(client, token_a)
    url = f"/skills/{skill['id']}{path_suffix}"

    if method == "GET":
        resp = await client.get(url, headers=auth_headers(token_b))
    else:
        resp = await client.post(url, headers=auth_headers(token_b), json=payload)

    assert resp.status_code == 404


async def test_cross_org_list_never_shows_other_org_skills(client, two_orgs):
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")
    token_b = await login(client, org_b, "owner")

    skill_a = await create_draft_skill(client, token_a, slug="only-in-org-a")
    await create_draft_skill(client, token_b, slug="only-in-org-b")

    list_a = await client.get("/skills", headers=auth_headers(token_a))
    slugs_a = {s["slug"] for s in list_a.json()}
    assert "only-in-org-a" in slugs_a
    assert "only-in-org-b" not in slugs_a
    assert skill_a["id"] in {s["id"] for s in list_a.json()}


async def test_audit_log_is_scoped_to_caller_org(client, two_orgs):
    org_a, org_b = two_orgs
    token_a = await login(client, org_a, "owner")
    token_b = await login(client, org_b, "owner")

    skill_a = await create_draft_skill(client, token_a)
    await create_draft_skill(client, token_b)

    audit_b = await client.get("/audit", headers=auth_headers(token_b))
    assert all(row["skill_id"] != skill_a["id"] for row in audit_b.json())
