# Organization-Scoped Skill Registry — Vertical Slice

A privacy-first, multi-tenant backend where organizations draft, review, and activate their own "AI COO" skills — with strict organization-level isolation and immutable version history. Built for the Jarvis AI COO developer evaluation; see [docs/ADR.md](docs/ADR.md) for the architecture decisions behind it.

## Stack

FastAPI · PostgreSQL 16 (Row-Level Security) · SQLAlchemy 2.0 (async) · Alembic · Pydantic v2 · PyJWT · Argon2 · pytest

## Quick start

```bash
cp .env.example .env          # placeholders are fine for local use
make up                       # builds images, runs migrations, seeds fixtures, starts the API
```

The API is now at `http://localhost:8000` — interactive docs at `/docs`, health check at `/api/v1/health`.

Run the required end-to-end workflow (login → draft → review → activate → retrieve → audit):

```bash
make demo
```

Run the full test suite (dockerized, against a disposable Postgres):

```bash
make test
```

Tear everything down (including the database volume):

```bash
make down
```

## Docker setup

Everything runs in containers — no local Python/Postgres install needed, just Docker and Docker Compose. [docker-compose.yml](docker-compose.yml) defines four services, chained via `depends_on`:

| Service | What it does |
|---|---|
| `postgres` | Postgres 16, exposed on `5432`, backed by a named volume (`pgdata`) so data survives container restarts |
| `migrate` | Runs `alembic upgrade head` (schema + RLS policies/triggers) against the superuser role, then exits |
| `seed` | Runs `scripts/seed_fixtures.py` (idempotent — skips orgs that already exist), then exits |
| `api` | The FastAPI app itself (`uvicorn app.main:app`), exposed on `8000` |

`make up` is shorthand for building all four images and bringing them up in the right order; the [Makefile](Makefile) targets map directly to plain `docker compose` commands if you'd rather run them yourself:

```bash
docker compose build                        # build all images
docker compose run --rm migrate             # apply migrations only
docker compose run --rm seed                # seed fixtures only
docker compose up -d api                    # start just the API (after migrate has run)
docker compose logs -f api                  # tail API logs
docker compose ps                           # see what's running
```

**After changing code**, rebuild and restart the `api` image for the change to take effect:

```bash
docker compose build api
docker compose up -d api
```

(`migrate` runs again automatically as `api`'s dependency — this is a no-op if the schema is already at `head`, so it won't disturb existing data.)

**Tests use a separate Postgres session state, not a separate container.** `make test` (see below) reuses the *same* `postgres` service/volume as `make up` via [docker-compose.test.yml](docker-compose.test.yml) as a compose override — the test suite manages its own schema/data during the run, which will clear out your fixture data. If you've been testing manually (via Swagger/curl) and then run `make test`, run `make seed` again afterward to restore the fixture users.

## Fixture organizations

`scripts/seed_fixtures.py` (run automatically by `make up`) seeds the two organizations named in the evaluation brief, each with an owner/admin/member user and one department:

| Organization | Slug | Department |
|---|---|---|
| ABC Construction | `abc-construction` | Operations (`operations`) |
| XYZ Builders | `xyz-builders` | Field Ops (`field-ops`) |

Every seeded user's password is `FixtureDemoPass123!` (printed again at the end of the seed script). Emails follow `{role}@{org-slug}.test`, e.g. `owner@abc-construction.test`, `admin@abc-construction.test`, `member@abc-construction.test`.

## API examples

```bash
BASE=http://localhost:8000/api/v1

# 1. Log in (tenant is selected explicitly, by slug, at login — see docs/ADR.md ADR-8)
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"organization_slug":"abc-construction","email":"owner@abc-construction.test","password":"FixtureDemoPass123!"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Create a skill draft (this also creates version 1)
curl -s -X POST "$BASE/skills" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "slug": "weekly-ops-report",
  "name": "Weekly Ops Report",
  "department_slug": "operations",
  "instructions": "Compile the weekly site status into a structured report.",
  "requested_tools": ["reports.generate", "docs.read"]
}'

# 3. Review (approve) version 1
curl -s -X POST "$BASE/skills/<skill_id>/versions/1/review" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"decision": "approve"}'

# 4. Owner activates version 1 (idempotent — repeat calls return the same result)
curl -s -X POST "$BASE/skills/<skill_id>/versions/1/activate" -H "Authorization: Bearer $TOKEN"

# 5. Retrieve active skills for a department (tools resolved against org grants)
curl -s "$BASE/runtime/skills?department=operations" -H "Authorization: Bearer $TOKEN"

# 6. Exact version audit record
curl -s "$BASE/audit?skill_id=<skill_id>" -H "Authorization: Bearer $TOKEN"
```

Full route list, request/response schemas: `http://localhost:8000/docs` once running.

## Isolation evidence (how to convince yourself)

1. Log in as `owner@xyz-builders.test` and `GET /skills/<abc-construction-skill-id>` — **404**, not 403 (see [docs/ADR.md](docs/ADR.md) ADR-4 for why).
2. `tests/security/test_isolation.py` — cross-org read/update/activate, body-`organization_id` injection, a parametrized sweep of every skill-scoped route with a foreign id.
3. `tests/security/test_rls_db_level.py` — connects directly as the same restricted Postgres role (`app_role`) the API uses and proves via raw SQL that Postgres itself, independent of any application code, will not return or accept cross-tenant rows.
4. `tests/security/test_auth.py` — forged signatures, tampered claims, expired tokens.

Run `make test` and see `docs/TEST_OUTPUT.md` for the full captured run.

## Repository layout

```
app/
├── main.py            # FastAPI app factory, middleware, exception handlers
├── core/               # config, logging, request-id, RFC 9457 problem+json errors
├── db/                 # SQLAlchemy models, session/engine (RLS-aware)
├── security/           # password hashing, JWT, Principal + RLS context wiring
├── repositories/        # org-scoped data access (the isolation seam)
├── domain/              # skill lifecycle, tool catalog, audit — testable without HTTP
├── schemas/             # Pydantic request/response models
└── api/v1/              # thin FastAPI routers
alembic/versions/        # 0001 schema, 0002 RLS policies + immutability/audit triggers
scripts/                 # seed_fixtures.py, demo_workflow.sh
tests/{unit,integration,security}/
docs/                    # ADR, limitations, test output, final report
```

## Architecture decision note

See [docs/ADR.md](docs/ADR.md) — nine numbered decisions covering: Postgres + RLS, token-only tenant context, the four-layer isolation model, why cross-tenant access is 404 not 403, the write-once version pointer model, requested-vs-granted tools, in-transaction audit writes, local JWT auth, and the thin-router/fat-service split.

## Known limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Restrictions honored

No proprietary code copied, no real customer/company data (fixtures are the two named fictional organizations only), no hardcoded secrets (`.env.example` has placeholders only), no frontend, no external AI/model API, no automatic skill activation, no cross-tenant admin/superuser shortcut anywhere in the codebase.
