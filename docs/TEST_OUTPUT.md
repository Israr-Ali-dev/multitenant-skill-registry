# Test Output

Captured verbatim from `make test` (`docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test`), run against a disposable Postgres 16 container. Docker Compose log prefixes stripped for readability; content otherwise unedited. Re-captured against `main` at `619f2ce` (after the HTTPBearer security-scheme and Swagger-example fixes) — numbers are unchanged from the original capture, confirming those were doc/OpenAPI-only changes with no behavioral impact.

**Result: 44 passed, 0 failed. 95% line coverage on `app/`.**

All 10 mandatory tests from the evaluation brief are covered by name in the run below (`test_same_org_create_and_read_succeeds`, `test_cross_org_read_denied`, `test_cross_org_update_denied`, `test_non_owner_activation_denied`, `test_draft_skill_excluded_from_runtime`, `test_disabled_skill_excluded_from_runtime`, `test_active_version_is_immutable`, `test_duplicate_activation_is_idempotent`, `test_destructive_tool_is_rejected`, `test_audit_record_contains_org_actor_event_version`), plus the isolation/auth/RLS/unit extras in `tests/security/` and `tests/unit/`.

```
 Container multitenant-skill-registry-postgres-1  Running
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-8.3.3, pluggy-1.6.0 -- /usr/local/bin/python3.12
cachedir: .pytest_cache
rootdir: /app
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, asyncio-0.24.0, cov-5.0.0
asyncio: mode=Mode.AUTO, default_loop_scope=None
collecting ... collected 44 items

tests/integration/test_skills_lifecycle.py::test_same_org_create_and_read_succeeds PASSED [  2%]
tests/integration/test_skills_lifecycle.py::test_draft_skill_excluded_from_runtime PASSED [  4%]
tests/integration/test_skills_lifecycle.py::test_disabled_skill_excluded_from_runtime PASSED [  6%]
tests/integration/test_skills_lifecycle.py::test_active_version_is_immutable PASSED [  9%]
tests/integration/test_skills_lifecycle.py::test_duplicate_activation_is_idempotent PASSED [ 11%]
tests/integration/test_skills_lifecycle.py::test_concurrent_duplicate_activation_is_still_idempotent PASSED [ 13%]
tests/integration/test_skills_lifecycle.py::test_destructive_tool_is_rejected PASSED [ 15%]
tests/integration/test_skills_lifecycle.py::test_audit_record_contains_org_actor_event_version PASSED [ 18%]
tests/integration/test_skills_lifecycle.py::test_activation_requires_approved_version PASSED [ 20%]
tests/integration/test_skills_lifecycle.py::test_new_version_on_disabled_skill_is_rejected PASSED [ 22%]
tests/integration/test_skills_lifecycle.py::test_second_version_increments_number_and_starts_as_draft PASSED [ 25%]
tests/integration/test_workflow_e2e.py::test_required_end_to_end_workflow PASSED [ 27%]
tests/security/test_auth.py::test_login_wrong_password_rejected PASSED   [ 29%]
tests/security/test_auth.py::test_login_wrong_organization_slug_rejected PASSED [ 31%]
tests/security/test_auth.py::test_login_user_from_other_org_with_right_password_rejected PASSED [ 34%]
tests/security/test_auth.py::test_missing_authorization_header_rejected PASSED [ 36%]
tests/security/test_auth.py::test_malformed_authorization_header_rejected PASSED [ 38%]
tests/security/test_auth.py::test_token_signed_with_wrong_secret_rejected PASSED [ 40%]
tests/security/test_auth.py::test_token_with_swapped_org_id_claim_rejected PASSED [ 43%]
tests/security/test_auth.py::test_expired_token_rejected PASSED          [ 45%]
tests/security/test_isolation.py::test_cross_org_read_denied PASSED      [ 47%]
tests/security/test_isolation.py::test_cross_org_update_denied PASSED    [ 50%]
tests/security/test_isolation.py::test_non_owner_activation_denied PASSED [ 52%]
tests/security/test_isolation.py::test_body_organization_id_is_ignored PASSED [ 54%]
tests/security/test_isolation.py::test_cross_org_route_sweep_returns_404[GET--None] PASSED [ 56%]
tests/security/test_isolation.py::test_cross_org_route_sweep_returns_404[POST-/versions-payload1] PASSED [ 59%]
tests/security/test_isolation.py::test_cross_org_route_sweep_returns_404[POST-/versions/1/review-payload2] PASSED [ 61%]
tests/security/test_isolation.py::test_cross_org_route_sweep_returns_404[POST-/versions/1/activate-None] PASSED [ 63%]
tests/security/test_isolation.py::test_cross_org_route_sweep_returns_404[POST-/disable-None] PASSED [ 65%]
tests/security/test_isolation.py::test_cross_org_list_never_shows_other_org_skills PASSED [ 68%]
tests/security/test_isolation.py::test_audit_log_is_scoped_to_caller_org PASSED [ 70%]
tests/security/test_rls_db_level.py::test_rls_blocks_cross_org_select_at_the_database_level PASSED [ 72%]
tests/security/test_rls_db_level.py::test_rls_fails_closed_with_no_org_context_set PASSED [ 75%]
tests/security/test_rls_db_level.py::test_rls_blocks_cross_org_insert_at_the_database_level PASSED [ 77%]
tests/security/test_rls_db_level.py::test_audit_logs_reject_update_and_delete PASSED [ 79%]
tests/unit/test_audit_service.py::test_record_captures_org_actor_event_and_version PASSED [ 81%]
tests/unit/test_tool_catalog.py::test_known_safe_tools_pass_through PASSED [ 84%]
tests/unit/test_tool_catalog.py::test_empty_list_is_valid PASSED         [ 86%]
tests/unit/test_tool_catalog.py::test_destructive_tools_rejected[shell.exec] PASSED [ 88%]
tests/unit/test_tool_catalog.py::test_destructive_tools_rejected[db.drop_table] PASSED [ 90%]
tests/unit/test_tool_catalog.py::test_destructive_tools_rejected[files.delete_recursive] PASSED [ 93%]
tests/unit/test_tool_catalog.py::test_unknown_tool_rejected PASSED       [ 95%]
tests/unit/test_tool_catalog.py::test_duplicate_tool_rejected PASSED     [ 97%]
tests/unit/test_tool_catalog.py::test_too_many_tools_rejected PASSED     [100%]

---------- coverage: platform linux, python 3.12.14-final-0 ----------
Name                                 Stmts   Miss  Cover   Missing
------------------------------------------------------------------
app/__init__.py                          0      0   100%
app/api/__init__.py                      0      0   100%
app/api/deps.py                         12      3    75%   11-16
app/api/v1/__init__.py                   8      0   100%
app/api/v1/audit.py                     13      0   100%
app/api/v1/auth.py                      30      3    90%   48-52
app/api/v1/health.py                     9      3    67%   11-13
app/api/v1/runtime.py                   11      0   100%
app/api/v1/skills.py                    40      0   100%
app/core/__init__.py                     0      0   100%
app/core/config.py                      16      0   100%
app/core/errors.py                      60      4    93%   118-122, 145-146
app/core/logging.py                      4      0   100%
app/core/request_context.py             13      0   100%
app/db/__init__.py                       0      0   100%
app/db/base.py                           7      0   100%
app/db/models/__init__.py                8      0   100%
app/db/models/audit_log.py              21      0   100%
app/db/models/department.py             15      0   100%
app/db/models/organization.py           13      0   100%
app/db/models/skill.py                  21      0   100%
app/db/models/skill_version.py          23      0   100%
app/db/models/tool_grant.py             15      0   100%
app/db/models/user.py                   17      0   100%
app/db/session.py                       13      0   100%
app/domain/__init__.py                   0      0   100%
app/domain/audit_service.py              8      0   100%
app/domain/skill_service.py            126     12    90%   51, 73, 217, 224, 227, 262, 269, 272, 323, 328, 366, 371
app/domain/tool_catalog.py              24      0   100%
app/main.py                             12      0   100%
app/repositories/__init__.py             0      0   100%
app/repositories/audit_logs.py          13      0   100%
app/repositories/departments.py         10      2    80%   19-22
app/repositories/organizations.py        6      0   100%
app/repositories/skill_versions.py      18      0   100%
app/repositories/skills.py              21      0   100%
app/repositories/tool_grants.py          7      0   100%
app/repositories/users.py                7      0   100%
app/schemas/__init__.py                  0      0   100%
app/schemas/audit.py                    16      0   100%
app/schemas/auth.py                     15      0   100%
app/schemas/common.py                    8      8     0%   1-10
app/schemas/skill.py                    65      0   100%
app/security/__init__.py                 0      0   100%
app/security/hashing.py                 12      2    83%   16-17
app/security/jwt.py                     18      0   100%
app/security/principal.py               37      3    92%   48-49, 65
------------------------------------------------------------------
TOTAL                                  792     40    95%

======================= 44 passed, 4 warnings in 24.88s ========================
```

Notes on what's omitted above: three `UserWarning`s from Pydantic about the `model_params` field name colliding with its "protected namespace" convention (cosmetic; not a bug — silencing it would mean setting `protected_namespaces = ()` in the affected schemas) and one `DeprecationWarning` about `tests/conftest.py`'s custom `event_loop` fixture (used deliberately — see the comment at its definition — to keep the production engine and the test admin engine, both created once at import time, bound to a single event loop for the whole session; pytest-asyncio's per-test default loop would otherwise break every test after the first with "attached to a different loop"). `app/schemas/common.py`'s `ProblemDetail` model shows 0% because it documents the error response shape for OpenAPI but is never constructed directly in code — every error response is built in `app/core/errors.py` (93% covered) instead.

`app/api/v1/auth.py` is now 30 statements (was 29) and `app/security/principal.py`'s coverage-excluded lines shifted slightly — both are the direct result of the `HTTPBearer` security-scheme change (see commit `7d25ee6`); no other file's statement count moved, confirming the rest of that change set (the two `docs(api):` commits) touched OpenAPI metadata only.

## Bugs this test run caught and fixed while building

Recorded here because they're a direct product of actually running the suite against real Postgres rather than trusting the code by inspection:

1. **`reviewed_at` (and other datetime columns) bound as naive timestamps against `timestamptz` columns.** SQLAlchemy's `Mapped[datetime]` doesn't default to timezone-aware; asyncpg rejected the tz-aware `datetime.now(timezone.utc)` this codebase actually sends. Fixed with a `type_annotation_map` on `Base` (`app/db/base.py`) so every `datetime` column is `DateTime(timezone=True)` by default.
2. **`disable_skill` returned a `Skill` whose `updated_at` was left expired after `flush()`** (an `onupdate=func.now()` column isn't eagerly re-fetched by SQLAlchemy the way `server_default` is on insert) — synchronous Pydantic serialization then tried to lazy-load it outside the async context. Fixed with an explicit `await db.refresh(skill)`.
3. **`validate_requested_tools` de-duplicated through a `set()`, silently reordering the tool list.** Fixed to de-duplicate while preserving input order.

All three were caught by `make demo` / `make test` failing, not by code review — see [docs/LIMITATIONS.md](LIMITATIONS.md) and [docs/ADR.md](ADR.md) for the design; this file is the evidence it actually runs.
