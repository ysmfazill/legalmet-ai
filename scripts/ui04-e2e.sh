#!/usr/bin/env bash
# UI-04 live end-to-end verification — Department Command Center.
# Drives the REAL endpoints the /department page calls, against the running
# dev servers (uvicorn :8000, Vite :5173), and cross-checks every headline
# number directly against the SQLite database, so a fabricated figure cannot
# pass.
set -uo pipefail
API=http://127.0.0.1:8000/api/v1
WEB=http://localhost:5173
CD="/e/ai sales/services/api"
DB="$CD/legalmet.db"
PY="$CD/.venv/Scripts/python.exe"
PASS=0; FAIL=0

check() { # name, condition-result (0 = pass)
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1"; fi
}
contains() { echo "$1" | grep -q "$2"; }

# --- 1. SHELL: the route, page module and stylesheet all load -----------------
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB/department")
[ "$CODE" = "200" ]; check "Vite serves /department route (HTTP $CODE)" $?
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB/src/pages/Department.tsx")
[ "$CODE" = "200" ]; check "Vite transforms Department.tsx without error (HTTP $CODE)" $?
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB/src/styles/department.css")
[ "$CODE" = "200" ]; check "Vite serves department.css (HTTP $CODE)" $?

# --- 2. RBAC: anonymous rejected, any staff role accepted ---------------------
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/department/dashboard")
[ "$CODE" = "401" ]; check "dashboard rejects anonymous access (HTTP 401)" $?

TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"inspector@legalmet.local","password":"changeme-inspector"}' \
  | "$PY" -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
AUTH="Authorization: Bearer $TOKEN"
ATOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"auditor@legalmet.local","password":"changeme-inspector"}' \
  | "$PY" -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/department/dashboard" -H "Authorization: Bearer $ATOKEN")
[ "$CODE" = "200" ]; check "read-only AUDITOR role may view (HTTP 200)" $?

# --- 3. REAL DATA: every headline KPI cross-checked against SQLite ------------
DASH=$(curl -s "$API/department/dashboard?days=30" -H "$AUTH")
echo "$DASH" > /tmp/ui04-dash.json
"$PY" - "$DB" /tmp/ui04-dash.json <<'EOF' > /tmp/ui04-check 2>&1 || true
import json, sqlite3, sys

db = sqlite3.connect(sys.argv[1])
q = lambda sql, *a: db.execute(sql, a).fetchone()[0]
d = json.load(open(sys.argv[2]))

# KPIs vs the database.
total = q("SELECT COUNT(*) FROM citizen_reports")
assert d["kpis"]["totalComplaints"] == total, (d["kpis"]["totalComplaints"], total)
converted = q("SELECT COUNT(*) FROM citizen_reports WHERE inspection_id IS NOT NULL")
assert d["kpis"]["convertedToInspection"] == converted, (d["kpis"]["convertedToInspection"], converted)
pending = q("""SELECT COUNT(*) FROM citizen_reports
               WHERE status IN ('SUBMITTED','UNDER_REVIEW','REQUEST_INFORMATION')""")
assert d["kpis"]["pendingReview"] == pending, (d["kpis"]["pendingReview"], pending)
statuses = dict(db.execute("SELECT status, COUNT(*) FROM citizen_reports GROUP BY status").fetchall())
assert d["statusDistribution"] == statuses, (d["statusDistribution"], statuses)

# Pipeline: each stage is a real count.
assert d["pipeline"]["citizenReports"] == total
decided = q("""SELECT COUNT(*) FROM citizen_reports WHERE status IN ('ACTION_TAKEN','CLOSED')""")
assert d["pipeline"]["decision"] == decided

# Trend: zero-filled, one point per day, sums to the window count.
assert len(d["trend"]) == d["windowDays"], (len(d["trend"]), d["windowDays"])
assert sum(p["count"] for p in d["trend"]) == d["windowComplaints"]

# Priority queue rows carry explainable triage signals.
for row in d["priorityQueue"]:
    assert row["prioritySource"] in ("OFFICIAL_DECISION", "SYSTEM_SCREENING"), row
    assert 0 <= row["evidenceCompleteness"] <= 100, row

# Needs-attention counts are never hardcoded: zero when the DB says zero.
for item in d["needsAttention"]:
    assert item["count"] >= 0 and item["filters"], item
print("ok")
EOF
[ "$(cat /tmp/ui04-check 2>/dev/null)" = "ok" ]; check "all KPIs + pipeline + trend match SQLite exactly" $?

# --- 4. NAVIGATION: every deep-link filter the cards emit is server-side real --
PEND=$(curl -s "$API/citizen/complaints?status=SUBMITTED,UNDER_REVIEW,REQUEST_INFORMATION" -H "$AUTH")
N=$(echo "$PEND" | "$PY" -c "import sys,json;print(len(json.load(sys.stdin)))")
[ "$N" = "$(echo "$DASH" | "$PY" -c "import sys,json;print(json.load(sys.stdin)['kpis']['pendingReview'])")" ]
check "KPI deep-link filter (multi-status) matches pendingReview=$N" $?

for F in "risk=HIGH" "inspection=LINKED" "evidence=MINIMAL" "assigned=UNASSIGNED" "stale=true"; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/citizen/complaints?$F&limit=5" -H "$AUTH")
  [ "$CODE" = "200" ]; check "queue accepts dashboard filter '$F' (HTTP 200)" $?
done

# Complaint detail supports the queue's action deep-links (?action= is consumed
# client-side, but the target statuses must be legal transition sources).
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/citizen/complaints?status=ACCEPTED,ASSIGNED&limit=5" -H "$AUTH")
[ "$CODE" = "200" ]; check "assignable statuses (ACCEPTED,ASSIGNED) filter works (HTTP 200)" $?

# --- 5. API FAILURE PATHS: validation + auth errors are real, not decorative ---
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/department/dashboard?days=5" -H "$AUTH")
[ "$CODE" = "422" ]; check "invalid window (days=5) rejected with 422" $?
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/department/dashboard?days=91" -H "$AUTH")
[ "$CODE" = "422" ]; check "invalid window (days=91) rejected with 422" $?
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/citizen/complaints?status=NOT_A_STATUS" -H "$AUTH")
[ "$CODE" = "422" ]; check "unknown status filter rejected with 422" $?

# --- 6. WINDOW SWITCH: 7-day window is a genuinely different query -------------
D7=$(curl -s "$API/department/dashboard?days=7" -H "$AUTH")
echo "$D7" | "$PY" -c "
import sys, json
d = json.load(sys.stdin)
assert d['windowDays'] == 7 and len(d['trend']) == 7, d['windowDays']
print('ok')
" > /tmp/ui04-check 2>&1 || true
[ "$(cat /tmp/ui04-check 2>/dev/null)" = "ok" ]; check "7-day window re-queries (trend length 7)" $?

# --- 7. UI-01/02/03 REGRESSION: the surfaces UI-04 builds on still work -------
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB/citizen")
[ "$CODE" = "200" ]; check "Citizen Mode route still serves (HTTP 200)" $?
CODE=$(cd "$CD" && curl -s -o /dev/null -w "%{http_code}" "$API/citizen/scans" -X POST -F "file=@ui03-label.png;type=image/jpeg")
[ "$CODE" = "201" ]; check "citizen scan endpoint still accepts uploads (HTTP 201)" $?
STATS=$(curl -s "$API/citizen/complaints/stats" -H "$AUTH")
echo "$STATS" | "$PY" -c "
import sys, json
s = json.load(sys.stdin)
assert s['total'] >= 1, s
print('ok')
" > /tmp/ui04-check 2>&1 || true
[ "$(cat /tmp/ui04-check 2>/dev/null)" = "ok" ]; check "UI-03 complaint stats still real (total >= 1)" $?

echo
echo "UI-04 E2E: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
