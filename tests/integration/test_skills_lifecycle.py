"""Domain/version lifecycle tests — covers mandatory items 1, 5, 6, 7, 8, 9, 10
(see PLAN.md section 6) plus a handful of extra lifecycle edge cases.
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import auth_headers, create_draft_skill, login


async def test_same_org_create_and_read_succeeds(client: AsyncClient, two_orgs):
    """Mandatory #1: same-organization create/read succeeds."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")

    skill = await create_draft_skill(client, token)

    read_resp = await client.get(f"/skills/{skill['id']}", headers=auth_headers(token))
    assert read_resp.status_code == 200
    body = read_resp.json()
    assert body["id"] == skill["id"]
    assert body["status"] == "draft"
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version_number"] == 1


async def test_draft_skill_excluded_from_runtime(client: AsyncClient, two_orgs):
    """Mandatory #5: draft skill cannot execute or load as active."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)

    runtime_resp = await client.get("/runtime/skills", headers=auth_headers(token))
    assert runtime_resp.status_code == 200
    assert all(s["skill_id"] != skill["id"] for s in runtime_resp.json())


async def test_disabled_skill_excluded_from_runtime(client: AsyncClient, two_orgs):
    """Mandatory #6: disabled skill is excluded from runtime selection."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)

    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(token),
        json={"decision": "approve"},
    )
    await client.post(f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token))

    runtime_before = await client.get("/runtime/skills", headers=auth_headers(token))
    assert any(s["skill_id"] == skill["id"] for s in runtime_before.json())

    disable_resp = await client.post(f"/skills/{skill['id']}/disable", headers=auth_headers(token))
    assert disable_resp.status_code == 200
    assert disable_resp.json()["status"] == "disabled"

    runtime_after = await client.get("/runtime/skills", headers=auth_headers(token))
    assert all(s["skill_id"] != skill["id"] for s in runtime_after.json())


async def test_active_version_is_immutable(client: AsyncClient, two_orgs):
    """Mandatory #7: active version is immutable.

    There is no HTTP route that mutates version content at all (verified by
    contract below); as a second, independent enforcement layer, a direct SQL
    UPDATE against the content columns is rejected by a DB trigger even for a
    write-privileged connection.
    """
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)
    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(token),
        json={"decision": "approve"},
    )
    await client.post(f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token))

    # No route exists to PATCH/PUT a version's content — contract check.
    patch_resp = await client.patch(
        f"/skills/{skill['id']}/versions/1",
        headers=auth_headers(token),
        json={"instructions": "changed"},
    )
    assert patch_resp.status_code in (404, 405)

    detail = (await client.get(f"/skills/{skill['id']}", headers=auth_headers(token))).json()
    version_id = detail["versions"][0]["id"]

    # Direct SQL attempt against the immutable columns must raise, even for
    # a write-privileged (table-owner) connection.
    from tests.conftest import _admin_engine

    with pytest.raises(Exception, match="immutable"):
        async with _admin_engine.begin() as conn:
            await conn.execute(
                text("UPDATE skill_versions SET instructions = 'tampered' WHERE id = :id"),
                {"id": version_id},
            )


async def test_duplicate_activation_is_idempotent(client: AsyncClient, two_orgs):
    """Mandatory #8: duplicate activation request is safe and idempotent."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)
    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(token),
        json={"decision": "approve"},
    )

    first = await client.post(
        f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)
    )
    assert first.status_code == 200
    assert first.json()["idempotent"] is False

    second = await client.post(
        f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)
    )
    assert second.status_code == 200
    assert second.json()["idempotent"] is True

    audit_resp = await client.get(
        f"/audit?skill_id={skill['id']}", headers=auth_headers(token)
    )
    activated_events = [e for e in audit_resp.json() if e["event"] == "skill.activated"]
    noop_events = [e for e in audit_resp.json() if e["event"] == "skill.activate.noop"]
    assert len(activated_events) == 1
    assert len(noop_events) == 1


async def test_concurrent_duplicate_activation_is_still_idempotent(client: AsyncClient, two_orgs):
    """Two simultaneous activation requests for the same version: exactly one
    'activated' audit event is ever recorded, thanks to the row-level lock.
    """
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)
    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(token),
        json={"decision": "approve"},
    )

    responses = await asyncio.gather(
        client.post(f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)),
        client.post(f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)),
    )
    assert all(r.status_code == 200 for r in responses)
    idempotent_flags = sorted(r.json()["idempotent"] for r in responses)
    assert idempotent_flags == [False, True]

    audit_resp = await client.get(
        f"/audit?skill_id={skill['id']}", headers=auth_headers(token)
    )
    activated_events = [e for e in audit_resp.json() if e["event"] == "skill.activated"]
    assert len(activated_events) == 1


async def test_destructive_tool_is_rejected(client: AsyncClient, two_orgs):
    """Mandatory #9: invalid or destructive requested tool is rejected."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")

    destructive_resp = await client.post(
        "/skills",
        headers=auth_headers(token),
        json={
            "slug": "dangerous-skill",
            "name": "Dangerous",
            "instructions": "do stuff",
            "requested_tools": ["shell.exec"],
        },
    )
    assert destructive_resp.status_code == 422
    body = destructive_resp.json()
    assert body["type"].endswith("tool-not-permitted")
    assert any(e["code"] == "tool_destructive" for e in body["errors"])

    unknown_resp = await client.post(
        "/skills",
        headers=auth_headers(token),
        json={
            "slug": "unknown-tool-skill",
            "name": "Unknown",
            "instructions": "do stuff",
            "requested_tools": ["totally.made_up_tool"],
        },
    )
    assert unknown_resp.status_code == 422
    assert any(e["code"] == "unknown_tool" for e in unknown_resp.json()["errors"])


async def test_audit_record_contains_org_actor_event_version(client: AsyncClient, two_orgs):
    """Mandatory #10: audit record contains organization, actor, event and version."""
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)

    audit_resp = await client.get(
        f"/audit?skill_id={skill['id']}", headers=auth_headers(token)
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) >= 1
    for entry in entries:
        assert entry["organization_id"] == str(org_a.org.id)
        assert entry["actor_role"] in ("owner", "admin", "member")
        assert entry["event"]
        assert entry["skill_id"] == skill["id"]
        # "version" is present on the entries this test cares about (creation).
        assert entry["version_number"] == 1


async def test_activation_requires_approved_version(client: AsyncClient, two_orgs):
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)

    resp = await client.post(
        f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token)
    )
    assert resp.status_code == 409


async def test_new_version_on_disabled_skill_is_rejected(client: AsyncClient, two_orgs):
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)
    await client.post(
        f"/skills/{skill['id']}/versions/1/review",
        headers=auth_headers(token),
        json={"decision": "approve"},
    )
    await client.post(f"/skills/{skill['id']}/versions/1/activate", headers=auth_headers(token))
    await client.post(f"/skills/{skill['id']}/disable", headers=auth_headers(token))

    resp = await client.post(
        f"/skills/{skill['id']}/versions",
        headers=auth_headers(token),
        json={"instructions": "new content", "requested_tools": []},
    )
    assert resp.status_code == 409


async def test_second_version_increments_number_and_starts_as_draft(
    client: AsyncClient, two_orgs
):
    org_a, _ = two_orgs
    token = await login(client, org_a, "owner")
    skill = await create_draft_skill(client, token)

    v2_resp = await client.post(
        f"/skills/{skill['id']}/versions",
        headers=auth_headers(token),
        json={"instructions": "revised instructions", "requested_tools": ["docs.read"]},
    )
    assert v2_resp.status_code == 201
    v2 = v2_resp.json()
    assert v2["version_number"] == 2
    assert v2["review_state"] == "draft"
