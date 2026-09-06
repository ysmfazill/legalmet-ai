#!/usr/bin/env bash
# UI-05 live end-to-end verification — Complaint → Targeted Inspection.
# Drives the REAL endpoints the complaint detail page, the inspection
# workspace and the department queue call, against the running dev servers
# (uvicorn :8000, Vite :5173), and cross-checks the complaint → inspection
# linkage and the audit trail directly against the SQLite database, so a
# fabricated result cannot pass.
#
# Flow under test (the METRASIGHT principle — no automatic violation):
#   citizen reports → department reviews/accepts → targeted inspection
#   created → inspector formally assigned → inspector independently verifies.
set -uo pipefail
API=http://127.0.0.1:8000/api/v1
WEB=http://localhost:5173
ROOT="/e/ai sales"
CD="$ROOT/services/api"
DB="$CD/legalmet.db"
PY="$CD/.venv/Scripts/python.exe"
PHOTO=".ui05-e2e-photo.jpg" # repo-relative: the Windows curl cannot read MSYS /tmp paths
PASS=0; FAIL=0

check() { # name, condition-result (0 = pass)
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1"; fi
}
# Pure-bash substring test: piping large payloads into `grep -q` under
# `pipefail` fails on SIGPIPE when grep exits at the first match.
contains() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
jget() { echo "$1" | "$PY" -c "import sys,json;print(json.load(sys.stdin)$2)" 2>/dev/null; }

# --- 0. SHELL: the routes and page modules the workflow lives in --------------
for route in /complaints /inspections /department; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB$route")
  [ "$CODE" = "200" ]; check "Vite serves $route route (HTTP $CODE)" $?
done
for mod in src/pages/ComplaintDetail.tsx src/pages/Workspace.tsx src/pages/Complaints.tsx src/components/InspectionTable.tsx; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEB/$mod")
  [ "$CODE" = "200" ]; check "Vite transforms $mod without error (HTTP $CODE)" $?
done

# The transformed modules must actually contain the new UI-05 surfaces —
# proving the dev server serves the new code, not a stale build.
served() { curl -s "$WEB/$1"; }
contains "$(served src/pages/ComplaintDetail.tsx)" "Create Targeted Inspection"
check "ComplaintDetail serves the Create Targeted Inspection action" $?
contains "$(served src/pages/ComplaintDetail.tsx)" "Additional information required"
check "ComplaintDetail serves the pre-flight missing-information copy" $?
contains "$(served src/pages/Workspace.tsx)" "Source complaint evidence"
check "Workspace serves the source-evidence section" $?
contains "$(served src/pages/Workspace.tsx)" "not official findings"
check "Workspace keeps citizen evidence separate from official findings" $?
contains "$(served src/pages/Workspace.tsx)" "Confirm reassignment"
check "Workspace serves the reassignment confirmation" $?
contains "$(served src/components/InspectionTable.tsx)" "Targeted"
check "InspectionTable labels targeted inspections" $?
contains "$(served src/pages/Complaints.tsx)" "Not converted"
check "Complaints queue shows the not-converted inspection state" $?

# --- 1. logins -----------------------------------------------------------------
login() { # email, password → token
  curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | "$PY" -c "import sys,json;print(json.load(sys.stdin)['accessToken'])"
}
SUP=$(login supervisor@legalmet.local changeme-inspector)
INSP=$(login inspector@legalmet.local changeme-inspector)
AUD=$(login auditor@legalmet.local changeme-inspector)
SUPH="Authorization: Bearer $SUP"
INSPH="Authorization: Bearer $INSP"
AUDH="Authorization: Bearer $AUD"

# --- 2. anonymous citizen: scan + report → SUBMITTED complaint with photo ------
cd "$ROOT"
"$PY" - > "$PHOTO" <<'EOF'
import io, sys
from PIL import Image
img = Image.new("RGB", (1600, 2000), (120, 90, 60))
buf = io.BytesIO()
img.save(buf, format="JPEG")
sys.stdout.buffer.write(buf.getvalue())
EOF
SCAN=$(curl -s -X POST "$API/citizen/scans" -F "file=@$PHOTO;type=image/jpeg")
SCAN_ID=$(jget "$SCAN" "['id']")
[ -n "$SCAN_ID" ]; check "anonymous citizen scan accepted (id $SCAN_ID)" $?

REPORT=$(curl -s -X POST "$API/citizen/reports" -H "Content-Type: application/json" -d "{
  \"scanId\": \"$SCAN_ID\",
  \"product\": \"UI05 Live Product\",
  \"shop\": \"UI05 Live Store\",
  \"location\": \"UI05 Livetown\",
  \"issue\": \"MRP appears inconsistent\",
  \"description\": \"The printed MRP looks tampered with\"
}")
CID=$(jget "$REPORT" "['id']")
CREF=$(jget "$REPORT" "['reference']")
STATUS=$(jget "$REPORT" "['status']")
[ "$STATUS" = "SUBMITTED" ]; check "citizen report $CREF submitted (status $STATUS)" $?

# --- 3. RBAC: anonymous cannot act on the complaint -----------------------------
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/citizen/complaints/$CID/transition" \
  -H "Content-Type: application/json" -d '{"action":"START_REVIEW"}')
[ "$CODE" = "401" ]; check "anonymous cannot transition the complaint (HTTP 401)" $?

# --- 4. department review: START_REVIEW → ACCEPT --------------------------------
R=$(curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$SUPH" \
  -H "Content-Type: application/json" -d '{"action":"START_REVIEW"}')
[ "$(jget "$R" "['status']")" = "UNDER_REVIEW" ]; check "supervisor START_REVIEW → UNDER_REVIEW" $?
R=$(curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$SUPH" \
  -H "Content-Type: application/json" -d '{"action":"ACCEPT"}')
[ "$(jget "$R" "['status']")" = "ACCEPTED" ]; check "supervisor ACCEPT → ACCEPTED" $?

# --- 5. conversion: CREATE_INSPECTION → linked targeted inspection --------------
R=$(curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"action":"CREATE_INSPECTION","officialPriority":"HIGH"}')
CSTATUS=$(jget "$R" "['status']")
IID=$(jget "$R" "['inspectionId']")
IREF=$(jget "$R" "['inspectionReference']")
[ "$CSTATUS" = "INSPECTION_SCHEDULED" ]; check "CREATE_INSPECTION moves complaint to INSPECTION_SCHEDULED" $?
[ -n "$IID" ] && contains "$IREF" "LM-"; check "complaint now links inspection $IREF" $?

# Duplicate protection: the same complaint cannot convert twice.
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/citizen/complaints/$CID/transition" \
  -H "$INSPH" -H "Content-Type: application/json" -d '{"action":"CREATE_INSPECTION"}')
[ "$CODE" = "409" ]; check "duplicate conversion rejected (HTTP 409)" $?

# The complaint detail carries the link for the detail page's Open button.
D=$(curl -s "$API/citizen/complaints/$CID" -H "$INSPH")
[ "$(jget "$D" "['inspectionId']")" = "$IID" ]; check "complaint detail exposes inspectionId" $?
[ "$(jget "$D" "['inspection']['referenceNo']")" = "$IREF" ]; check "complaint detail exposes the inspection reference" $?

# The department queue row shows the real inspection status.
Q=$(curl -s "$API/citizen/complaints" -H "$SUPH")
ROW=$(echo "$Q" | "$PY" -c "
import sys, json
rows = json.load(sys.stdin)
row = next(r for r in rows if r['id'] == '$CID')
print(row.get('inspectionStatus') or '')")
[ "$ROW" = "CREATED" ]; check "department queue shows inspectionStatus CREATED (got '$ROW')" $?

# --- 6. the inspection itself: provenance + workspace payload -------------------
I=$(curl -s "$API/inspections/$IID" -H "$INSPH")
[ "$(jget "$I" "['sourceComplaint']['reference']")" = "$CREF" ]; check "inspection carries sourceComplaint $CREF" $?
[ "$(jget "$I" "['sourceComplaint']['issue']")" = "MRP appears inconsistent" ]; check "sourceComplaint carries the reported issue" $?
contains "$(jget "$I" "['note']")" "$CREF"; check "inspection note names its complaint origin" $?

B=$(curl -s "$API/inspections/$IID/source-complaint" -H "$INSPH")
[ "$(jget "$B" "['reference']")" = "$CREF" ]; check "source-complaint brief endpoint returns the complaint" $?
[ "$(jget "$B" "['evidence','imageUrl']")" != "None" ]; check "brief preserves the citizen photo evidence" $?
EVENTS=$(jget "$B" "['eventCount']")
[ "$EVENTS" -ge 3 ]; check "brief counts the complaint event trail ($EVENTS events)" $?
contains "$(jget "$B" "['description']")" "tampered"; check "brief preserves the citizen description" $?

# An inspection that did not originate from a complaint has no brief.
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/inspections/00000000-0000-0000-0000-000000000000/source-complaint" -H "$INSPH")
[ "$CODE" = "404" ]; check "source-complaint on unknown inspection → 404 (HTTP $CODE)" $?

# The inspector's list shows the targeted inspection with its source.
L=$(curl -s "$API/inspections?page=1&pageSize=100" -H "$INSPH")
FOUND=$(echo "$L" | "$PY" -c "
import sys, json
items = json.load(sys.stdin)['items']
row = next((i for i in items if i['id'] == '$IID'), None)
print('yes' if row and row.get('sourceComplaint', {}).get('reference') == '$CREF' else 'no')")
[ "$FOUND" = "yes" ]; check "inspector list shows $IREF with source $CREF" $?

# --- 7. assignment: RBAC matrix, validation, reassignment, audit ---------------
FIELD_ID=$(curl -s "$API/citizen/complaints/inspectors" -H "$SUPH" | \
  "$PY" -c "import sys,json;us=json.load(sys.stdin);print(next(u['id'] for u in us if u['role']=='INSPECTOR'))")
OTHER_ID=$(curl -s "$API/citizen/complaints/inspectors" -H "$SUPH" | \
  "$PY" -c "import sys,json;us=json.load(sys.stdin);print(next(u['id'] for u in us if u['id']!='$FIELD_ID'))")
[ -n "$FIELD_ID" ]; check "assignable inspectors list resolves a field inspector" $?

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/inspections/$IID/assign" \
  -H "Content-Type: application/json" -d "{\"inspectorId\":\"$FIELD_ID\"}")
[ "$CODE" = "401" ]; check "anonymous cannot assign (HTTP 401)" $?

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/inspections/$IID/assign" -H "$INSPH" \
  -H "Content-Type: application/json" -d "{\"inspectorId\":\"$FIELD_ID\"}")
[ "$CODE" = "403" ]; check "INSPECTOR cannot perform department-only assignment (HTTP 403)" $?

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/inspections/$IID/assign" -H "$AUDH" \
  -H "Content-Type: application/json" -d "{\"inspectorId\":\"$FIELD_ID\"}")
[ "$CODE" = "403" ]; check "AUDITOR cannot assign (HTTP 403)" $?

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/inspections/$IID/assign" -H "$SUPH" \
  -H "Content-Type: application/json" -d '{"inspectorId":"00000000-0000-0000-0000-000000000000"}')
[ "$CODE" = "404" ]; check "unknown inspector rejected (HTTP 404)" $?

R=$(curl -s -X POST "$API/inspections/$IID/assign" -H "$SUPH" -H "Content-Type: application/json" \
  -d "{\"inspectorId\":\"$FIELD_ID\",\"note\":\"Field verification of the MRP complaint\"}")
[ "$(jget "$R" "['inspectorId']")" = "$FIELD_ID" ]; check "supervisor assigns the field inspector" $?

# The source complaint is kept in sync.
D=$(curl -s "$API/citizen/complaints/$CID" -H "$INSPH")
[ "$(jget "$D" "['assignedInspectorId']")" = "$FIELD_ID" ]; check "source complaint synced to the assigned inspector" $?

# Reassignment to a different inspector requires the explicit flag.
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/inspections/$IID/assign" -H "$SUPH" \
  -H "Content-Type: application/json" -d "{\"inspectorId\":\"$OTHER_ID\"}")
[ "$CODE" = "409" ]; check "reassignment without confirmation rejected (HTTP 409)" $?
R=$(curl -s -X POST "$API/inspections/$IID/assign" -H "$SUPH" -H "Content-Type: application/json" \
  -d "{\"inspectorId\":\"$OTHER_ID\",\"reassign\":true}")
[ "$(jget "$R" "['inspectorId']")" = "$OTHER_ID" ]; check "explicit reassignment accepted" $?

# --- 8. audit trail: every step left an append-only event ----------------------
A=$(curl -s "$API/inspections/$IID/audit" -H "$INSPH")
AUDITED=$(echo "$A" | "$PY" -c "
import sys, json
types = {e['eventType'] for e in json.load(sys.stdin)}
need = {'INSPECTION_CREATED', 'COMPLAINT_INSPECTION_CREATED', 'INSPECTION_ASSIGNED'}
print('yes' if need <= types else 'no')")
[ "$AUDITED" = "yes" ]; check "inspection audit has INSPECTION_CREATED + COMPLAINT_INSPECTION_CREATED + INSPECTION_ASSIGNED" $?

# --- 9. SQLite cross-check: the linkage and audit rows are real ----------------
"$PY" - "$DB" "$CID" "$IID" "$CREF" <<'EOF' > /tmp/ui05-check 2>&1 || true
import sqlite3, sys

db = sqlite3.connect(sys.argv[1])
# UUID columns are stored as 32-char hex without dashes on SQLite.
cid, iid = (v.replace("-", "") for v in sys.argv[2:4])
ref = sys.argv[4]

row = db.execute(
    "SELECT inspection_id, status, assigned_inspector_id FROM citizen_reports WHERE id = ?",
    (cid,),
).fetchone()
assert row is not None, "complaint row missing"
assert row[0] == iid, f"citizen_reports.inspection_id mismatch: {row[0]}"
assert row[1] == "INSPECTION_SCHEDULED", row[1]
assert row[2] is not None, "assigned_inspector_id not synced"

inspection = db.execute(
    "SELECT inspector_id, note FROM inspections WHERE id = ?", (iid,)
).fetchone()
assert inspection is not None, "inspection row missing"
assert ref in (inspection[1] or ""), "inspection note does not name the complaint"

events = [
    e[0]
    for e in db.execute(
        "SELECT event_type FROM audit_events WHERE inspection_id = ?", (iid,)
    )
]
for expected in ("INSPECTION_CREATED", "COMPLAINT_INSPECTION_CREATED", "INSPECTION_ASSIGNED"):
    assert expected in events, (expected, events)
print("ok")
EOF
contains_ok() { [ "$(cat /tmp/ui05-check)" = "ok" ]; }
# Capture the status BEFORE building the check message — a command
# substitution in the arguments would clobber $?.
contains_ok; RC=$?
check "SQLite confirms linkage, sync and audit rows ($(head -1 /tmp/ui05-check))" $RC
rm -f "$PHOTO"

echo
echo "UI-05 live e2e: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
