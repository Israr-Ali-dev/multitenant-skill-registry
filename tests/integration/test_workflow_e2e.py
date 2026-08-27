"""The exact required end-to-end workflow (evaluation brief, section 3):

    authenticated organization -> manual skill draft create -> draft review
    -> owner activation -> active skill retrieve -> exact version audit record

Mirrors scripts/demo_workflow.sh so both the automated suite and the manual
demo prove the same path.
"""

from httpx import AsyncClient

from tests.conftest import auth_headers, login


async def test_required_end_to_end_workflow(client: AsyncClient, two_orgs):
    org_a, _org_b = two_orgs

    # 1. Authenticated organization (owner logs in)
    owner_token = await login(client, org_a, "owner")

    # 2. Manual skill draft create
    create_resp = await client.post(
        "/skills",
        headers=auth_headers(owner_token),
        json={
            "slug": "weekly-ops-report",
            "name": "Weekly Ops Report",
            "description": "Summarizes weekly site progress for ops leadership.",
            "department_slug": org_a.department.slug,
            "instructions": "Compile the weekly site status into a structured report.",
            "model_params": {"temperature": 0.2},
            "requested_tools": ["docs.read"],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    skill = create_resp.json()
    assert skill["status"] == "draft"
    skill_id = skill["id"]

    # 3. Draft review (approve version 1)
    review_resp = await client.post(
        f"/skills/{skill_id}/versions/1/review",
        headers=auth_headers(owner_token),
        json={"decision": "approve", "notes": "Looks good."},
    )
    assert review_resp.status_code == 200, review_resp.text
    assert review_resp.json()["review_state"] == "approved"

    # 4. Owner activation
    activate_resp = await client.post(
        f"/skills/{skill_id}/versions/1/activate", headers=auth_headers(owner_token)
    )
    assert activate_resp.status_code == 200, activate_resp.text
    activation = activate_resp.json()
    assert activation["status"] == "active"
    assert activation["active_version_number"] == 1
    assert activation["idempotent"] is False

    # 5. Active skill retrieve (both the detail view and the runtime view)
    detail_resp = await client.get(f"/skills/{skill_id}", headers=auth_headers(owner_token))
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "active"

    runtime_resp = await client.get(
        f"/runtime/skills?department={org_a.department.slug}", headers=auth_headers(owner_token)
    )
    assert runtime_resp.status_code == 200
    runtime_skills = runtime_resp.json()
    assert any(s["skill_id"] == skill_id for s in runtime_skills)
    active_entry = next(s for s in runtime_skills if s["skill_id"] == skill_id)
    assert active_entry["version_number"] == 1
    assert active_entry["tools"] == [{"tool": "docs.read", "granted": False}]  # not yet granted

    # 6. Exact version audit record
    audit_resp = await client.get(
        f"/audit?skill_id={skill_id}", headers=auth_headers(owner_token)
    )
    assert audit_resp.status_code == 200
    events = {row["event"] for row in audit_resp.json()}
    expected_events = {
        "skill.created",
        "skill.version.created",
        "skill.version.approved",
        "skill.activated",
    }
    assert expected_events <= events

    activated_entry = next(row for row in audit_resp.json() if row["event"] == "skill.activated")
    assert activated_entry["skill_id"] == skill_id
    assert activated_entry["version_number"] == 1
    assert activated_entry["actor_role"] == "owner"
