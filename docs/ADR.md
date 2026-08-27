# Architecture Decision Records

Numbered decisions for the Organization-Scoped Skill Registry vertical slice. See [PLAN.md](../PLAN.md) for the full design rationale these summarize.

## ADR-1: PostgreSQL 16, not SQLite

Postgres is the spec's preferred choice. It also provides three things this design leans on directly: **JSONB** (`model_params`, `requested_tools`, audit `detail`), **Row-Level Security** (the RLS isolation layer), and **`SELECT ... FOR UPDATE`** row locking (safe concurrent activation). SQLite supports none of the three natively. No written justification is needed since Postgres is the preferred option, not a deviation from it.

## ADR-2: Tenant context comes only from the verified JWT

`organization_id` is never accepted from a path parameter, query string, or request body. `SkillCreateRequest` and every other write schema has no such field; if a client sends one anyway, Pydantic silently drops it as an unrecognized field. The only place `organization_id` is ever written into a token is at login (`app/security/jwt.py::create_access_token`), from the authenticated user's own row. Every subsequent request re-derives it by verifying the JWT signature (`app/security/principal.py`). See `tests/security/test_isolation.py::test_body_organization_id_is_ignored`.

## ADR-3: Defense in depth — four independent isolation layers

1. **Token-derived context** — ADR-2.
2. **Org-scoped repository layer** — every query in `app/repositories/*.py` filters explicitly by `organization_id`, even though layer 4 would also block a leak.
3. **Composite foreign keys** — `(child_id, organization_id) → (parent_id, organization_id)` on `skills`, `skill_versions`, and the `active_version_id` pointer make a cross-tenant row *link* unrepresentable in the schema itself, not just unreachable via the API.
4. **Postgres Row-Level Security** — the API connects exclusively as `app_role`, a non-superuser, non-table-owner login role created in migration `0002`. RLS is bypassed for superusers and table owners by Postgres design; connecting as neither is what makes the policies actually bind. Policies fail closed: `organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid` evaluates to `NULL` (never true) if the session variable was never set, so a session that forgot to scope itself sees zero rows, not everyone's.

Any one layer failing is a defect to fix, not a breach — see `tests/security/test_rls_db_level.py` for layer 4 tested in isolation from the other three.

## ADR-4: Cross-tenant access returns 404, not 403

A `403 Forbidden` confirms a resource exists but the caller lacks permission — an enumeration oracle across tenant boundaries. Every repository lookup (`app/repositories/skills.py::get_by_id`, etc.) is `WHERE id = :id AND organization_id = :caller_org`; a foreign-tenant row simply doesn't match and the service layer raises `NotFoundError` → 404. `403` is reserved for *in-tenant* permission failures (e.g. a member attempting to activate), where the caller already knows the resource exists.

## ADR-5: `skill_versions` rows are write-once

`skills.active_version_id` is the single pointer to "what's live." Activating a version means `UPDATE skills SET active_version_id = :v, status = 'active'` — it never writes to `skill_versions`. Enforced three ways: (a) no route or service method updates version content, (b) a `BEFORE UPDATE` trigger (migration `0002`) raises unless the only changed columns are `review_state`/`reviewed_by`/`reviewed_at`, (c) `content_hash` is a SHA-256 of the canonicalized content, computed once at creation.

## ADR-6: Requested tools ≠ granted tools

A skill version declares `requested_tools`. Actual capability grants live in a separate, org-scoped `tool_grants` table, populated independently of any version. `app/domain/skill_service.py::runtime_active_skills` resolves `granted: bool` per tool by checking membership in the org's grant set — a version can request `email.send` forever and it stays `granted: false` until an owner explicitly grants it to the org. Additionally, `app/domain/tool_catalog.py` rejects unknown or `destructive`-flagged tool keys (`shell.exec`, `db.drop_table`, `files.delete_recursive`, `network.raw_socket`) at request time, regardless of grants.

## ADR-7: Audit writes share the mutation's transaction

`app/domain/audit_service.py::record` never opens its own session or commits — it stages an `AuditLog` row on the caller's existing `AsyncSession`. Since every mutating service function (`create_skill_draft`, `activate_version`, etc.) calls it before returning, and the request's single transaction commits or rolls back atomically (`app/db/session.py::get_db_session`), an audit entry for an action that then fails, and a successful action with no audit entry, are both impossible. The `audit_logs` table is additionally append-only: a trigger blocks `UPDATE`/`DELETE` outright, and `app_role`'s Postgres grant excludes those privileges entirely (belt and suspenders).

## ADR-8: Local HS256 JWT auth with seeded fixture users

No external AI/API is required or used (per spec). Login (`POST /auth/login`) takes `organization_slug` + `email` + `password` — tenant selection is explicit, the same pattern used by Slack/GitHub-style multi-workspace logins, and it's also what resolves the chicken-and-egg problem of looking up a user before any JWT (hence RLS context) exists: the org is looked up by slug first (the `organizations` table itself carries no RLS, since it *is* the tenant boundary, not tenant-owned data), then the session's RLS context is set to that org before the user lookup runs. Passwords are hashed with Argon2id (`argon2-cffi`). Tokens are HS256, 60-minute expiry by default, carrying `sub` (user id), `org_id`, and `role`. A stale or role-mismatched token is rejected even if the signature is valid (`app/security/principal.py` re-checks the user's current row).

## ADR-9: Service layer holds domain rules; routers stay thin

`app/api/v1/*.py` routers only map HTTP ↔ schemas and wire dependencies (`Depends(get_current_principal)`, `Depends(require_owner)`). All lifecycle invariants — review-state gating, owner-only activation, idempotent re-activation, disabled-skill rejection — live in `app/domain/skill_service.py`, which takes a `Principal` and an `AsyncSession` and is fully testable without any HTTP machinery (see `tests/unit/`). Role checks are enforced in *both* the router dependency and the service function deliberately — the router dependency gives a clean 403 early and correct OpenAPI docs; the service-level check is defense in depth against a future route being wired without it.
