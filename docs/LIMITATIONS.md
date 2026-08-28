# Known Limitations

- **Single shared HS256 JWT secret.** No refresh tokens, key rotation, or revocation list — an issued token is valid until it expires (default 60 minutes) or the underlying user is deactivated/role-changed (checked on every request).
- **No rate limiting or brute-force lockout** on `/auth/login` or any other endpoint.
- **Skills are stored and resolved, not executed.** There is no model runtime in this slice, by design (per spec: no external AI/model API required) — `GET /runtime/skills` returns the resolved instructions/params/tool-grants an executor *would* use, but nothing invokes a model.
- **Review workflow is single-step approve/reject.** No multi-approver policy, no reviewer comments thread, no diff view between versions.
- **Simple limit/offset-free listing.** `GET /skills` and `GET /audit` return the full org-scoped result set; no pagination. Fine at fixture scale, not at production scale.
- **RLS depends on the app never connecting as the table owner or a superuser.** Postgres RLS is bypassed for both regardless of policy — the safeguard here is that `docker-compose.yml` and `.env.example` wire the API exclusively to `app_role` (a non-owner login role created in migration `0002`), and migrations run separately as the owning role. A misconfigured deployment that pointed the API at the admin connection string would silently lose this layer (the other three isolation layers in ADR-3 would still hold).
- **No soft-delete or retention policy on `audit_logs`.** The table is append-only and grows without bound; there is no archival/export path in this slice (noted as a next step below).
- **Department is a flat first-class table**, not a hierarchy — no nested departments/teams.
- **No email verification / password reset flow** — fixture users are seeded directly with known credentials for evaluation purposes.

## What I would implement next

- Per-version diffing and rollback (revert active pointer to a prior approved version).
- An approval policy engine (N-of-M reviewers, required roles per department).
- A request/approval flow for `tool_grants` (currently owner-only, direct grant).
- A sandboxed execution path with per-tool capability tokens, so a skill's resolved tools are actually invocable, not just visible.
- Audit log export/streaming (e.g. to an external SIEM) and a retention/archival policy.
- Cursor-based pagination on list endpoints.
- Refresh tokens + a revocation list (e.g. a `token_version` column bumped on password change).
