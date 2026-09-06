#!/usr/bin/env bash
# UI-03 live end-to-end workflow test — drives the REAL API endpoints the
# frontend calls, against the running dev servers (uvicorn :8000, Vite :5173).
set -uo pipefail
API=http://127.0.0.1:8000/api/v1
CD="/e/ai sales/services/api"
PASS=0; FAIL=0

check() { # name, condition-result (0 = pass)
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1"; fi
}
contains() { echo "$1" | grep -q "$2"; }

# --- 1. CITIZEN: anonymous scan -> complaint ---------------------------------
SCAN=$(curl -s -X POST "$API/citizen/scans" -F "file=@ui03-label.png;type=image/jpeg")
SCAN_ID=$(echo "$SCAN" | "$CD/.venv/Scripts/python.exe" -c "import sys,json;print(json.load(sys.stdin)['id'])")
[ -n "$SCAN_ID" ]; check "citizen scan accepted (id=$SCAN_ID)" $?

REPORT=$(curl -s -X POST "$API/citizen/reports" -H "Content-Type: application/json" -d "{
  \"scanId\": \"$SCAN_ID\",
  \"product\": \"DEMO Wholesome Product\",
  \"shop\": \"Local store\",
  \"location\": \"Kothrud, Pune\",
  \"issue\": \"MRP may be unclear\",
  \"description\": \"Scratched MRP sticker\"
}")
REF=$(echo "$REPORT" | "$CD/.venv/Scripts/python.exe" -c "import sys,json;print(json.load(sys.stdin)['reference'])")
RID=$(echo "$REPORT" | "$CD/.venv/Scripts/python.exe" -c "import sys,json;print(json.load(sys.stdin)['id'])")
contains "$REF" "CMP-"; check "complaint created with backend-generated ID $REF" $?

# --- 2. CITIZEN: detail + real timeline --------------------------------------
DETAIL=$(curl -s "$API/citizen/reports/$RID")
echo "$DETAIL" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'SUBMITTED', d['status']
assert [e['event'] for e in d['events']] == ['SUBMITTED'], d['events']
assert d['events'][0]['actorType'] == 'CITIZEN'
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "citizen detail shows real timeline (SUBMITTED only)" $?

# --- 3. DEPARTMENT: login + real KPI counts ----------------------------------
TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"inspector@legalmet.local","password":"changeme-inspector"}' \
  | "$CD/.venv/Scripts/python.exe" -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
AUTH="Authorization: Bearer $TOKEN"
STATS=$(curl -s "$API/citizen/complaints/stats" -H "$AUTH")
echo "$STATS" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
s = json.load(sys.stdin)
assert s['submitted'] >= 1, s
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "dashboard KPIs are real counts (submitted >= 1)" $?

# --- 4. QUEUE: backend filtering ---------------------------------------------
FILTERED=$(curl -s "$API/citizen/complaints?status=SUBMITTED&search=$REF" -H "$AUTH")
N=$(echo "$FILTERED" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
items = json.load(sys.stdin)
assert len(items) == 1 and items[0]['reference'] == '$REF', items
print(len(items))
")
[ "$N" = "1" ]; check "queue backend filtering (status+search -> exactly this complaint)" $?

# --- 5. DEPARTMENT: complaint detail with evidence ----------------------------
CDETAIL=$(curl -s "$API/citizen/complaints/$RID" -H "$AUTH")
echo "$CDETAIL" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['evidence']['scanReference'].startswith('CS-'), d['evidence']
assert d['evidence']['imageUrl'], d['evidence']
assert d['screeningRisk'] in ('LOW','MEDIUM','HIGH'), d
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "complaint detail carries evidence + screening risk" $?

tr() { curl -s -X POST "$API/citizen/complaints/$RID/transition" -H "$AUTH" -H "Content-Type: application/json" -d "$1"; }

# --- 6. ACCEPT changes status (via review) ------------------------------------
R=$(tr '{"action":"START_REVIEW"}')
echo "$R" | "$CD/.venv/Scripts/python.exe" -c "import sys,json;assert json.load(sys.stdin)['status']=='UNDER_REVIEW'" 2>/dev/null
check "start review -> UNDER_REVIEW" $?

# --- 7. REQUEST INFORMATION -> citizen sees it --------------------------------
R=$(tr '{"action":"REQUEST_INFORMATION","reason":"A clearer photo of the MRP sticker is required."}')
echo "$R" | "$CD/.venv/Scripts/python.exe" -c "import sys,json;d=json.load(sys.stdin);assert d['status']=='REQUEST_INFORMATION' and d['pendingInfoRequest']" 2>/dev/null
check "request information -> REQUEST_INFORMATION" $?
CIT=$(curl -s "$API/citizen/reports/$RID")
echo "$CIT" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'REQUEST_INFORMATION'
assert 'MRP sticker' in d['pendingInfoRequest']
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "citizen sees the pending information request" $?

# --- 8. CITIZEN responds -> back to UNDER_REVIEW, evidence appended -----------
R=$(curl -s -X POST "$API/citizen/reports/$RID/respond" \
  -F "message=Here is a closer photo of the MRP sticker." \
  -F "location=Kothrud, Pune" \
  -F "file=@ui03-label.png;type=image/jpeg")
echo "$R" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'UNDER_REVIEW', d['status']
assert d['pendingInfoRequest'] is None
events = [e['event'] for e in d['events']]
assert 'INFORMATION_PROVIDED' in events, events
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "citizen response -> UNDER_REVIEW with appended evidence" $?
CDETAIL=$(curl -s "$API/citizen/complaints/$RID" -H "$AUTH")
echo "$CDETAIL" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
fups = d['evidence']['citizenFollowUps']
assert len(fups) == 1 and fups[0]['imageUrl'], d['evidence']
assert d['evidence']['scanReference'].startswith('CS-')  # original preserved
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "original evidence preserved (append-only)" $?

# --- 9. ACCEPT -> CREATE INSPECTION -> link verified ---------------------------
R=$(tr '{"action":"ACCEPT","officialPriority":"HIGH"}')
echo "$R" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'ACCEPTED', d['status']
assert d['officialPriority'] == 'HIGH', d
print('ok')
" > /tmp/ui03-check 2>&1 || true
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "accept -> ACCEPTED with official priority recorded" $?

R=$(tr '{"action":"CREATE_INSPECTION"}')
INS_ID=$(echo "$R" | "$CD/.venv/Scripts/python.exe" -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'INSPECTION_SCHEDULED', d['status']
assert d['inspection']['referenceNo'].startswith('LM-'), d['inspection']
print(d['inspection']['id'])
")
[ -n "$INS_ID" ]; check "create inspection -> INSPECTION_SCHEDULED, linked ${INS_ID:0:8}…" $?

# The link is real both ways (checked directly in the DB).
"$CD/.venv/Scripts/python.exe" - << PYEOF > /tmp/ui03-check 2>&1 || true
import sqlite3
db = sqlite3.connect(r"E:\\ai sales\\services\\api\\legalmet.db")
row = db.execute("SELECT reference, inspection_id, status FROM citizen_reports WHERE id = ?", ("$RID".replace("-", ""),)).fetchone()
assert row and row[1], row
ins = db.execute("SELECT reference_no, note FROM inspections WHERE id = ?", (row[1],)).fetchone()
assert ins and row[0] in (ins[1] or ""), ins
print("ok")
PYEOF
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "complaint -> inspection link verified in the database (both ways)" $?

# --- RBAC: auditor read-only --------------------------------------------------
ATOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"auditor@legalmet.local","password":"changeme-inspector"}' \
  | "$CD/.venv/Scripts/python.exe" -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/citizen/complaints/$RID/transition" \
  -H "Authorization: Bearer $ATOKEN" -H "Content-Type: application/json" -d '{"action":"CLOSE"}')
[ "$CODE" = "403" ]; check "RBAC: auditor cannot act on complaints (403)" $?

# --- Audit trail: real audit events recorded ----------------------------------
"$CD/.venv/Scripts/python.exe" - << PYEOF > /tmp/ui03-check 2>&1 || true
import sqlite3
db = sqlite3.connect(r"E:\\ai sales\\services\\api\\legalmet.db")
types = {r[0] for r in db.execute("SELECT event_type FROM audit_events").fetchall()}
for expected in ("COMPLAINT_REVIEW_STARTED", "COMPLAINT_INFO_REQUESTED", "CITIZEN_INFO_PROVIDED", "COMPLAINT_ACCEPTED", "COMPLAINT_INSPECTION_CREATED"):
    assert expected in types, expected
print("ok")
PYEOF
[ "$(cat /tmp/ui03-check 2>/dev/null)" = "ok" ]; check "audit trail records every complaint action" $?

# --- Vite dev server serves the new routes (SPA fallback + HMR alive) ---------
# (Vite binds to ::1 on this machine — localhost, not 127.0.0.1.)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5173/citizen/reports/$RID")
[ "$CODE" = "200" ]; check "Vite dev server serves /citizen/reports/:id (SPA fallback)" $?
CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5173/complaints/$RID")
[ "$CODE" = "200" ]; check "Vite dev server serves /complaints/:id (SPA fallback)" $?

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
exit $FAIL
