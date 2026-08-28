#!/usr/bin/env bash
# Exercises the required end-to-end workflow against a running API:
#   login -> draft create -> draft review -> owner activation
#   -> active skill retrieve -> exact version audit record
#
# Requires: `make up` (or `docker compose up`) already running, and
# `scripts/seed_fixtures.py` already applied (both are part of `make up`).
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"
PASSWORD="FixtureDemoPass123!"
ORG="abc-construction"

echo "== 1. Login as owner =="
OWNER_TOKEN=$(curl -sf -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"organization_slug\":\"$ORG\",\"email\":\"owner@$ORG.test\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  owner token acquired."

echo "== 2. Create a skill draft =="
SKILL_JSON=$(curl -sf -X POST "$BASE_URL/skills" \
  -H "Authorization: Bearer $OWNER_TOKEN" -H "Content-Type: application/json" \
  -d '{
        "slug": "weekly-ops-report",
        "name": "Weekly Ops Report",
        "description": "Summarizes weekly site progress for ops leadership.",
        "department_slug": "operations",
        "instructions": "Compile the weekly site status into a structured report.",
        "model_params": {"temperature": 0.2},
        "requested_tools": ["reports.generate", "docs.read"]
      }')
SKILL_ID=$(echo "$SKILL_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  created skill $SKILL_ID (status=draft, version=1)"

echo "== 3. Review (approve) version 1 =="
curl -sf -X POST "$BASE_URL/skills/$SKILL_ID/versions/1/review" \
  -H "Authorization: Bearer $OWNER_TOKEN" -H "Content-Type: application/json" \
  -d '{"decision": "approve", "notes": "Looks good."}' > /dev/null
echo "  version 1 approved."

echo "== 4. Owner activates version 1 =="
curl -sf -X POST "$BASE_URL/skills/$SKILL_ID/versions/1/activate" \
  -H "Authorization: Bearer $OWNER_TOKEN" | python3 -m json.tool

echo "== 5. Retrieve active skills (runtime view) =="
curl -sf "$BASE_URL/runtime/skills?department=operations" \
  -H "Authorization: Bearer $OWNER_TOKEN" | python3 -m json.tool

echo "== 6. Exact version audit record =="
curl -sf "$BASE_URL/audit?skill_id=$SKILL_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN" | python3 -m json.tool

echo "== Done. Workflow completed end-to-end. =="
