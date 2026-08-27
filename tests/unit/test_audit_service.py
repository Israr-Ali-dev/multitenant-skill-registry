import uuid

from app.domain import audit_service
from app.security.principal import Principal


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_record_captures_org_actor_event_and_version():
    session = _FakeSession()
    principal = Principal(
        user_id=uuid.uuid4(), organization_id=uuid.uuid4(), role="owner", email="o@test.local"
    )
    skill_id = uuid.uuid4()

    audit_service.record(
        session,
        principal=principal,
        event="skill.activated",
        resource_type="skill_version",
        resource_id=uuid.uuid4(),
        skill_id=skill_id,
        version_number=3,
        detail={"note": "test"},
        request_id="req-123",
    )

    assert len(session.added) == 1
    entry = session.added[0]
    assert entry.organization_id == principal.organization_id
    assert entry.actor_user_id == principal.user_id
    assert entry.actor_role == "owner"
    assert entry.event == "skill.activated"
    assert entry.skill_id == skill_id
    assert entry.version_number == 3
    assert entry.detail == {"note": "test"}
    assert entry.request_id == "req-123"
