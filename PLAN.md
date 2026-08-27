# Organization-Scoped Skill Registry — Vertical Slice

**Project plan / technical design.** No implementation yet — this document is the blueprint the code will follow.

- **Evaluation:** Jarvis AI COO — Developer Evaluation Task (8 hours)
- **Focus areas being scored:** tenant isolation & authorization (30), domain/version lifecycle (20), tests & failure handling (20), architecture/readability (15), setup & docs (10), git discipline & final report (5)

---

## 1. Problem statement

Multiple organizations create, review and activate their own AI COO "skills". Two hard guarantees:

1. **Isolation.** Org A can never read, update, or activate Org B's data — not via a crafted ID, not via a crafted body, not via a role escalation.
2. **Immutability.** An active skill version is never mutated in place. Every change is a new version, and activation is an explicit, owner-only, audited act.

Everything else (route naming, storage details, review workflow depth) is a design choice I own and must justify.

---

## 2. Architecture decisions (ADR summary)

These go into `docs/ADR.md` as short numbered records. Locked decisions:

| # | Decision | Rationale |
|---|---|---|
| ADR-1 | **PostgreSQL 16**, not SQLite | Preferred by spec; needed for JSONB, partial unique indexes, row-level security, and `FOR UPDATE` row locking used by activation. No written justification burden. |
| ADR-2 | **Tenant context comes only from the verified JWT** | `organization_id` is never accepted from path, query, or body. A client-supplied org id is either ignored or a 400 — it is structurally impossible to address another tenant. |
| ADR-3 | **Defense in depth: 4 isolation layers** | (a) token-derived context, (b) org-scoped repository layer, (c) composite constraints/FKs including `organization_id`, (d) Postgres RLS policies via `SET LOCAL app.current_org_id`. Any single layer failing is not a breach. |
| ADR-4 | **Cross-tenant access returns `404`, not `403`** | A 403 confirms the row exists and leaks tenant metadata (enumeration oracle). In-tenant permission failures (non-owner activating) return `403`, because existence is already known. Documented so it doesn't read as a bug. |
| ADR-5 | **`skill_versions` rows are write-once** | Content columns are immutable, enforced by a DB trigger, not just by the absence of an endpoint. The "which version is live" pointer lives on `skills.active_version_id`, so activation never writes to a version row. |
| ADR-6 | **Requested tools ≠ granted tools** | A version declares `requested_tools`. Grants live in a separate org-scoped `tool_grants` table. Effective capability = requested ∩ granted, resolved at read time. Requesting a tool grants nothing, ever. |
| ADR-7 | **Audit writes share the mutation's transaction** | An action that succeeds without an audit row, or an audit row for an action that rolled back, are both impossible. Audit table is append-only (trigger blocks UPDATE/DELETE). |
| ADR-8 | **Local HS256 JWT auth with seeded fixture users** | No external AI/API required by the spec, and none used. Auth is real (hashed passwords, signed tokens, expiry) but self-contained and reproducible. |
| ADR-9 | **Service layer holds domain rules; routers stay thin** | Routers = HTTP mapping + dependency wiring. Services = lifecycle invariants. Repositories = org-scoped data access. Testable without HTTP. |

**Open for the reviewer's preference (defaults chosen, easy to flip):** whether review approval is a distinct role (`admin` approves, `owner` activates) or owner-does-both; and whether `department` should be a first-class table (chosen) or a plain enum column.

---

## 3. Domain model

```
organizations ──┬── users            (role: owner | admin | member)
                ├── departments
                ├── tool_grants      (org-level capability allowlist)
                ├── skills ──── skill_versions   (write-once)
                └── audit_logs       (append-only)
```

**`skills` is the identity/container; `skill_versions` is the content.** Lifecycle status (`draft → active → disabled`) lives on the skill; review state lives on the version. This separation is what makes "an active skill is never modified in place" enforceable — activating flips a pointer on the skill row, and the version rows are never touched.

### Schema sketch

```sql
organizations(id uuid pk, name, slug unique, created_at)

users(id uuid pk, organization_id uuid fk, email, password_hash,
      role text check in ('owner','admin','member'), is_active bool, created_at,
      unique (organization_id, email))

departments(id uuid pk, organization_id uuid fk, name, slug, created_at,
      unique (organization_id, slug))

skills(id uuid pk, organization_id uuid fk, department_id uuid,
      slug, name, description,
      status text check in ('draft','active','disabled') default 'draft',
      active_version_id uuid null,          -- FK added deferred; single source of "live"
      created_by uuid, created_at, updated_at,
      unique (organization_id, slug),
      foreign key (department_id, organization_id)
          references departments(id, organization_id))   -- composite FK: cross-tenant link impossible

skill_versions(id uuid pk, organization_id uuid fk, skill_id uuid,
      version_number int,
      instructions text, model_params jsonb, requested_tools jsonb,
      content_hash text,                    -- sha256 of canonicalized content
      review_state text check in ('draft','in_review','approved','rejected') default 'draft',
      created_by uuid, reviewed_by uuid null, reviewed_at timestamptz null, created_at,
      unique (skill_id, version_number),
      foreign key (skill_id, organization_id) references skills(id, organization_id))

tool_grants(id uuid pk, organization_id uuid fk, tool_key text,
      granted_by uuid, granted_at, unique (organization_id, tool_key))

audit_logs(id bigserial pk, organization_id uuid, actor_user_id uuid, actor_role text,
      event text,                           -- skill.version.created, skill.activated, ...
      resource_type text, resource_id uuid,
      skill_id uuid null, version_number int null,
      detail jsonb, request_id text, created_at timestamptz default now())
```

**Constraint highlights the reviewer should see:**
- Composite FKs `(child_id, organization_id) → (parent_id, organization_id)` make a cross-tenant row graph unrepresentable at the DB level.
- `unique (organization_id, slug)` — two orgs can independently own a skill named `weekly-ops-report`.
- Partial index `unique (skill_id) where status = 'active'` is unnecessary given the pointer model, but `active_version_id` gets a check that it belongs to the same skill (trigger).
- RLS policy per tenant table: `USING (organization_id = current_setting('app.current_org_id')::uuid)`.

### Immutability enforcement (three independent mechanisms)

1. No route exists that updates version content.
2. `BEFORE UPDATE` trigger on `skill_versions` raises unless the only changed columns are `review_state / reviewed_by / reviewed_at`.
3. `content_hash` is recomputed and compared on read in the runtime path; a mismatch is a hard 500 + audit event.

---

## 4. Authorization model

```
request → verify JWT → Principal(user_id, organization_id, role)
        → SET LOCAL app.current_org_id (RLS)
        → org-scoped repository (every query filtered)
        → service-level rule check (role, lifecycle state)
```

| Capability | member | admin | owner |
|---|:--:|:--:|:--:|
| Create skill draft / new version | ✅ | ✅ | ✅ |
| List / read own-org skills | ✅ | ✅ | ✅ |
| Submit for review | ✅ | ✅ | ✅ |
| Approve / reject a version | ❌ | ✅ | ✅ |
| **Activate a version** | ❌ | ❌ | ✅ |
| Disable a skill | ❌ | ❌ | ✅ |
| Grant a tool to the org | ❌ | ❌ | ✅ |

No cross-tenant admin/superuser exists in the codebase at all — explicitly called out in the README, since the spec forbids the shortcut.

---

## 5. API surface

Base `/api/v1`. Org id appears in **no** route.

| Method | Route | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/login` | Issue JWT for a seeded fixture user | public |
| GET | `/auth/me` | Echo resolved principal (isolation evidence) | any |
| POST | `/skills` | Create skill + version 1 (`draft`) | any member |
| GET | `/skills` | List current org's skills (filter: status, department) | any |
| GET | `/skills/{skill_id}` | Skill + all versions | any (404 cross-org) |
| POST | `/skills/{skill_id}/versions` | Create next immutable version | any |
| POST | `/skills/{skill_id}/versions/{n}/review` | approve / reject | admin, owner |
| POST | `/skills/{skill_id}/versions/{n}/activate` | Activate approved version — **idempotent** | owner |
| POST | `/skills/{skill_id}/disable` | Disable skill | owner |
| GET | `/runtime/skills?department=ops` | Active skills only, tools resolved | any |
| GET | `/audit?skill_id=…` | Current org's audit trail | admin, owner |
| GET | `/health` | Liveness / DB check | public |

**Required end-to-end workflow maps to:** `login → POST /skills → POST …/review → POST …/activate → GET /runtime/skills → GET /audit`. This exact sequence ships as a `scripts/demo_workflow.sh` and as one integration test.

### Error contract

RFC 9457 `application/problem+json`:

```json
{ "type": "https://…/errors/tool-not-permitted", "title": "Requested tool is not allowed",
  "status": 422, "detail": "Tool 'shell.exec' is classified destructive and cannot be requested.",
  "errors": [{"field": "requested_tools[1]", "code": "tool_destructive"}],
  "request_id": "01J…" }
```

| Situation | Status |
|---|---|
| Missing/invalid/expired token | 401 |
| In-tenant role failure (member activating) | 403 |
| Cross-tenant resource, or genuinely missing | 404 |
| Schema/validation failure, destructive tool | 422 |
| Lifecycle violation (activate unapproved, version a disabled skill) | 409 |
| Duplicate activation of the already-active version | 200 (no-op, audited as `noop`) |

### Tool safety

`app/domain/tool_catalog.py` holds the known tool registry with a `destructive` flag. Rejection cases: unknown key → 422; `destructive: true` (e.g. `shell.exec`, `db.drop_table`, `files.delete_recursive`) → 422; duplicates/oversized list → 422. Accepted-but-ungranted tools are stored and surfaced at runtime as `pending_grant`, never as active capability.

---

## 6. Test plan

`pytest` + `pytest-asyncio` + `httpx.AsyncClient`, against a real Postgres container. Each test runs in a rolled-back transaction; fixtures seed **ABC Construction** and **XYZ Builders** with an owner, an admin, and a member each.

### Mandatory ten

| # | Requirement | Test | Expected |
|---|---|---|---|
| 1 | Same-org create/read succeeds | `test_same_org_create_and_read` | 201 → 200, correct payload |
| 2 | Cross-org read denied | `test_cross_org_read_denied` | 404, zero data leakage in body |
| 3 | Cross-org update denied | `test_cross_org_version_create_denied` | 404, no row written |
| 4 | Non-owner activation denied | `test_member_and_admin_cannot_activate` | 403, skill still `draft` |
| 5 | Draft never loads as active | `test_draft_excluded_from_runtime` | absent from `/runtime/skills` |
| 6 | Disabled excluded from runtime | `test_disabled_excluded_from_runtime` | absent after disable |
| 7 | Active version immutable | `test_active_version_immutable` | no mutating route; direct DB UPDATE raises trigger error |
| 8 | Duplicate activation idempotent | `test_activate_twice_is_idempotent` | 200 both times, one `activated` audit row + one `noop` |
| 9 | Destructive tool rejected | `test_destructive_tool_rejected` | 422, typed error code |
| 10 | Audit contains org/actor/event/version | `test_audit_record_shape` | all four fields asserted |

### Beyond the minimum (this is where the isolation marks live)

- **RLS proof:** with `app.current_org_id` set to Org A, a raw `SELECT * FROM skills` returns zero Org B rows.
- **Body-injection attack:** POST with `{"organization_id": "<org-b-uuid>"}` — ignored, resource lands in the caller's org.
- **Token forgery:** JWT signed with the wrong secret, and one with a swapped `org_id` claim → 401.
- **Concurrent activation:** two simultaneous activations of different versions → exactly one wins, audit is consistent.
- **Fuzz-ish sweep:** every route called with the other org's IDs, asserting 404 across the board (parametrized — cheap, high-signal).
- Audit table rejects UPDATE and DELETE.

Target: **>90% coverage on `app/domain` and `app/api`**. `pytest -v --cov` output is captured to `docs/TEST_OUTPUT.md` verbatim for the submission.

---

## 7. Repository layout

```
.
├── docker-compose.yml            # api + postgres(+ test profile)
├── Dockerfile
├── Makefile                      # up / down / test / lint / migrate / seed / demo
├── .env.example                  # placeholders ONLY
├── README.md                     # setup + curl examples + isolation evidence
├── PLAN.md                       # this file
├── docs/
│   ├── ADR.md                    # numbered architecture decisions
│   ├── TEST_OUTPUT.md            # pasted pytest run
│   ├── LIMITATIONS.md
│   └── FINAL_REPORT.md           # section 8 template, filled at the end
├── alembic/versions/             # migrations incl. RLS + triggers
├── app/
│   ├── main.py                   # app factory, middleware, exception handlers
│   ├── core/                     # config, logging, request-id, problem-details
│   ├── db/                       # engine, session, models/, rls.py
│   ├── security/                 # password hashing, jwt, principal, deps
│   ├── repositories/             # org-scoped data access (the isolation seam)
│   ├── domain/                   # skill_service, activation_service, tool_catalog, audit
│   ├── schemas/                  # pydantic v2 request/response
│   └── api/v1/                   # routers
├── scripts/                      # seed_fixtures.py, demo_workflow.sh
└── tests/{conftest.py,integration/,security/,unit/}
```

**Stack:** FastAPI · SQLAlchemy 2.0 async + asyncpg · Alembic · Pydantic v2 · PyJWT · argon2 (passlib) · pytest · ruff + mypy.

---

## 8. Eight-hour execution schedule

| Block | Duration | Output | Commit |
|---|---|---|---|
| 0 | 0:00–0:30 | Scaffold, Docker Compose, config, health check, CI-less lint setup | `chore: project scaffold + compose` |
| 1 | 0:30–1:30 | Models, migration 1 (tables, composite FKs, indexes) | `feat(db): tenant-scoped schema` |
| 2 | 1:30–2:00 | Migration 2: RLS policies + immutability & append-only triggers | `feat(db): RLS + immutability triggers` |
| 3 | 2:00–3:00 | Auth: hashing, JWT, principal dependency, RLS session wiring, fixture seed | `feat(auth): jwt principal + org context` |
| 4 | 3:00–4:30 | Skill/version CRUD, org-scoped repositories, tool catalog validation | `feat(skills): drafts + immutable versions` |
| 5 | 4:30–5:30 | Review, owner-only idempotent activation, disable, runtime selection | `feat(lifecycle): review, activation, runtime` |
| 6 | 5:30–6:00 | Audit service in-transaction + `/audit` endpoint | `feat(audit): in-transaction audit trail` |
| 7 | 6:00–7:15 | Full test suite (10 mandatory + isolation extras), fix fallout | `test: mandatory + isolation suite` |
| 8 | 7:15–8:00 | README, ADR, limitations, test output, final report, demo script | `docs: readme, adrs, final report` |

Slack is deliberate: blocks 4–5 are the likeliest to overrun. If time compresses, the order I cut is: `/audit` read endpoint (keep the writes), department filtering nuance, coverage extras. **Never cut:** the ten mandatory tests, RLS, the immutability trigger.

---

## 9. Guardrails against the automatic-rejection criteria

| Rejection trigger | Prevention |
|---|---|
| Committed secret | `.env` gitignored from commit 1; `.env.example` placeholders only; `gitleaks`/`detect-secrets` pass before final push; no secret ever in a test fixture or README |
| Cross-tenant leakage | Four enforcement layers + a parametrized cross-org sweep over every route |
| Fake tests | Every test asserts real state (DB rows + response), no `assert True`, no mocked service under test; coverage published |
| App fails to start | `docker compose up` → migrations → seed → `/health` green, verified from a clean clone before submission |
| Active skill silently mutated | No mutation route + DB trigger + `content_hash` verification + a test that attempts the raw UPDATE |

Also: no proprietary code, no real customer data (fixtures are the two named fictional orgs), no automatic activation anywhere in the code path, no admin bypass, no frontend, no external model API.

---

## 10. Known limitations (drafted now, finalized at submission)

- Single shared HS256 secret; no refresh tokens, rotation, or revocation list.
- No rate limiting, no request quotas, no brute-force lockout on `/auth/login`.
- Skills are stored and resolved but **not executed** — there is no model runtime in this slice, by design.
- Review workflow is single-step approve/reject; no multi-approver, no comments, no diff view between versions.
- Listing endpoints use simple limit/offset, not cursor pagination.
- RLS relies on the app never connecting as the table owner; a `BYPASSRLS` superuser connection would defeat it (the compose file provisions a non-owner app role to avoid exactly this).
- No soft-delete/retention policy on audit logs; the table grows unbounded.

**What I'd build next:** per-version diffing and rollback, an approval policy engine (N-of-M reviewers), org-level tool grant request/approval flow, background execution sandbox with per-tool capability tokens, and audit log export/streaming.

---

## 11. Submission checklist

- [ ] Source code + migrations
- [ ] Automated tests, all passing, output captured in `docs/TEST_OUTPUT.md`
- [ ] `docker compose up` works from a clean clone
- [ ] `.env.example` with placeholders only; secret scan clean
- [ ] README: setup, API examples (curl), isolation evidence section
- [ ] `docs/ADR.md` architecture note
- [ ] `docs/LIMITATIONS.md`
- [ ] `docs/FINAL_REPORT.md` — repo URL, start/finish time, hours, final commit SHA, goal achieved, decisions, tests passed, security evidence, limitations, next steps, AI tools used
- [ ] Meaningful commit history (~10–15 conventional commits, no single "initial commit" dump)
