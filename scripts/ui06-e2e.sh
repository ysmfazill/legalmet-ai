#!/usr/bin/env bash
# UI-06 live end-to-end verification — Inspector Workspace + Evidence Planner.
# Drives the REAL endpoints the workspace's Evidence Planner, Verification
# panel and Final Decision card call, against the running dev servers
# (uvicorn :8000, Vite :5173), and cross-checks the verification rows and the
# untouched declared value directly against the SQLite database, so a
# fabricated result cannot pass.
#
# Flow under test (SEE → UNDERSTAND → PROVE → DECIDE — no automatic violation):
#   complaint → targeted inspection → image intake → perception (real OCR)
#   → evaluation → evidence plan → REQUIRED verification task → decision gate
#   blocks → manual measurement recorded (declared value unchanged)
#   → gate opens → decision recorded → RECOMMENDED task never blocks.
set -uo pipefail
API=http://127.0.0.1:8000/api/v1
WEB=http://localhost:5173
ROOT="/e/ai sales"
CD="$ROOT/services/api"
DB="$CD/legalmet.db"
PY="$CD/.venv/Scripts/python.exe"
LABEL=".ui06-label.png" # repo-relative: the Windows curl cannot read MSYS /tmp paths
PASS=0; FAIL=0

check() { # name, condition-result (0 = pass)
  if [ "$2" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1"; fi
}
# Pure-bash substring test: piping large payloads into `grep -q` under
# `pipefail` fails on SIGPIPE when grep exits at the first match.
contains() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
jget() { echo "$1" | "$PY" -c "import sys,json;print(json.load(sys.stdin)$2)" 2>/dev/null; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

# --- 0. SHELL: the routes and modules the workflow lives in --------------------
for mod in src/evidence/EvidencePlannerLive.tsx src/evidence/VerificationPanel.tsx \
           src/evidence/EvidenceTimelineCard.tsx src/hitl/FinalDecisionCard.tsx \
           src/pages/Workspace.tsx src/pages/NewInspection.tsx; do
  C=$(code "$WEB/$mod")
  [ "$C" = "200" ]; check "Vite transforms $mod (HTTP $C)" $?
done
served() { curl -s "$WEB/$1"; }
contains "$(served src/evidence/VerificationPanel.tsx)" "Manual measurement entry"
check "VerificationPanel serves the MANUAL measurement-entry label" $?
contains "$(served src/evidence/VerificationPanel.tsx)" "not connected to a physical scale"
check "VerificationPanel states no hardware integration is pretended" $?
contains "$(served src/evidence/VerificationPanel.tsx)" "evaluate the measured value"
check "VerificationPanel never judges the declared-vs-measured difference" $?
contains "$(served src/evidence/EvidencePlannerLive.tsx)" "NOT a compliance verdict"
check "EvidencePlanner serves the gap-is-not-a-verdict banner" $?
contains "$(served src/hitl/FinalDecisionCard.tsx)" "evidence incomplete"
check "FinalDecisionCard serves the verification decision gate" $?
contains "$(served src/pages/Workspace.tsx)" "EvidencePlannerLive"
check "Workspace mounts the live evidence planner" $?
contains "$(served src/pages/Workspace.tsx)" "EvidenceTimelineCard"
check "Workspace mounts the evidence timeline" $?
contains "$(served src/pages/NewInspection.tsx)" "Evidence"
contains "$(served src/pages/NewInspection.tsx)" "Verify"
check "NewInspection stepper carries the Evidence + Verify steps" $?

# --- 1. logins ------------------------------------------------------------------
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

# --- 2. complaint → targeted inspection (checkpoint 8: source context) ---------
cd "$ROOT"
"$PY" - > .ui06-photo.jpg <<'EOF'
import io, sys
from PIL import Image
img = Image.new("RGB", (1200, 1600), (140, 100, 70))
buf = io.BytesIO(); img.save(buf, format="JPEG"); sys.stdout.buffer.write(buf.getvalue())
EOF
SCAN=$(curl -s -X POST "$API/citizen/scans" -F "file=@.ui06-photo.jpg;type=image/jpeg")
SCAN_ID=$(jget "$SCAN" "['id']")
REPORT=$(curl -s -X POST "$API/citizen/reports" -H "Content-Type: application/json" -d "{
  \"scanId\": \"$SCAN_ID\",
  \"product\": \"UI06 Live Detergent\",
  \"shop\": \"UI06 Live Store\",
  \"location\": \"UI06 Livetown\",
  \"issue\": \"Net quantity appears understated\",
  \"description\": \"The pack feels lighter than the 500 g declared on the label\"
}")
CID=$(jget "$REPORT" "['id']")
curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$SUPH" \
  -H "Content-Type: application/json" -d '{"action":"START_REVIEW"}' > /dev/null
curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$SUPH" \
  -H "Content-Type: application/json" -d '{"action":"ACCEPT"}' > /dev/null
R=$(curl -s -X POST "$API/citizen/complaints/$CID/transition" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"action":"CREATE_INSPECTION","officialPriority":"HIGH"}')
IID=$(jget "$R" "['inspectionId']")
[ -n "$IID" ]; check "targeted inspection created from the complaint (id $IID)" $?

# Formal assignment (supervisor) so the inspector may verify (UI-05 guard).
FIELD_ID=$(curl -s "$API/citizen/complaints/inspectors" -H "$SUPH" | \
  "$PY" -c "import sys,json;us=json.load(sys.stdin);print(next(u['id'] for u in us if u['role']=='INSPECTOR'))")
curl -s -X POST "$API/inspections/$IID/assign" -H "$SUPH" -H "Content-Type: application/json" \
  -d "{\"inspectorId\":\"$FIELD_ID\",\"note\":\"UI06 live evidence verification\"}" > /dev/null

# --- 3. intake: real label image → READY → perception (real OCR) ----------------
cd "$CD"
"$PY" - > "$LABEL" <<'EOF'
import sys
sys.path.insert(0, ".")
from tests.dataset.generate import _household_label, _render_plain
_render_plain(_household_label()).save(".ui06-label.png")
EOF
IMG=$(curl -s -X POST "$API/inspections/$IID/images/upload" -H "$INSPH" \
  -F "file=@$LABEL;type=image/png" -F "captureSource=UPLOAD" -F "imageType=FRONT")
IMG_ID=$(jget "$IMG" "['id']")
[ -n "$IMG_ID" ]; check "label image uploaded (id $IMG_ID)" $?
curl -s -X POST "$API/inspections/$IID/ready" -H "$INSPH" > /dev/null

K=$(curl -s -X POST "$API/inspections/$IID/perceive" -H "$INSPH")
KID=$(jget "$K" "['runs'][0]['runId']")
[ -n "$KID" ]; check "perception started (run $KID)" $?

# Poll until OCR + extraction have actually produced fields (real work, no fakes).
FIELDS=0
for i in $(seq 1 40); do
  A=$(curl -s "$API/inspections/$IID/analysis" -H "$INSPH")
  FIELDS=$(jget "$A" "['summary']['fieldsExtracted']" 2>/dev/null || echo 0)
  HAS=$(jget "$A" "['hasRuns']" 2>/dev/null || echo False)
  ACTIVE=$(jget "$A" "['active']" 2>/dev/null || echo True)
  if [ "$HAS" = "True" ] && [ "$ACTIVE" = "False" ] && [ "${FIELDS:-0}" -gt 0 ] 2>/dev/null; then break; fi
  sleep 2
done
[ "${FIELDS:-0}" -gt 0 ] 2>/dev/null; check "perception extracted $FIELDS declaration fields from real pixels" $?

# --- 4. evaluation: the deterministic engine runs over the evidence ------------
E=$(curl -s -X POST "$API/inspections/$IID/evaluate" -H "$INSPH")
ESTATUS=$(jget "$E" "['evaluation']['status']")
[ -n "$ESTATUS" ] && [ "$ESTATUS" != "NOT_EVALUATED" ]; check "evaluation recorded (status $ESTATUS)" $?

# Resolve any CRITICAL/MAJOR findings so the decision gate isolates the
# VERIFICATION blocker in the checks below (human review actions, as designed).
FJSON=$(curl -s "$API/inspections/$IID/compliance/findings" -H "$INSPH")
echo "$FJSON" | "$PY" -c "
import sys, json
for f in json.load(sys.stdin):
    if f.get('severity') in ('CRITICAL', 'MAJOR') and f.get('reviewState') in ('PENDING_REVIEW', None, 'UNREVIEWED'):
        print(f['id'])
" > .ui06-blocking-findings
while read -r FID || [ -n "$FID" ]; do
  # Windows python.exe writes CRLF line endings — strip the CR or the
  # review URL silently breaks (curl exit 6, swallowed by >/dev/null).
  FID=${FID%%$'\r'}
  [ -z "$FID" ] && continue
  curl -s -X POST "$API/compliance/findings/$FID/review" -H "$INSPH" \
    -H "Content-Type: application/json" -d '{"action":"CONFIRM"}' > /dev/null
done < .ui06-blocking-findings

# --- 5. THE EVIDENCE PLAN (checkpoint 2/3) ---------------------------------------
P=$(curl -s "$API/inspections/$IID/evidence-plan" -H "$INSPH")
echo "$P" | "$PY" -c "
import sys, json
p = json.load(sys.stdin)
items = p['items']
assert items, 'no plan rows'
row = next(r for r in items if any(g['kind'] == 'MEASUREMENT' for g in r['gaps']))
assert row['declaredValue'] == '500 g', row['declaredValue']
gap = next(g for g in row['gaps'] if g['kind'] == 'MEASUREMENT')
assert gap['required'] is True and gap['defaultLevel'] == 'REQUIRED', gap
assert 'DECLARED' in gap['reason'], gap['reason']
assert 'NOT a compliance verdict' in row['summary'], row['summary']
# No fabricated verdict, and the counts use the counts vocabulary
# (regression guard for the phantom-key bug).
assert p['counts']['requiringVerification'] >= 1, p['counts']
assert 'requiresVerification' not in p['counts'], p['counts']
print(row.get('fieldId') or row.get('findingId'))
" > .ui06-anchor 2>/tmp/ui06-planerr || true
ANCHOR=$(cat .ui06-anchor)
[ -n "$ANCHOR" ]; check "evidence plan: declared 500 g, MEASUREMENT gap REQUIRED, camera-cannot-weigh reason, no verdict" $? || cat /tmp/ui06-planerr

# RBAC on the plan + tasks (checkpoint 9: unauthorized actions fail).
C=$(code "$API/inspections/$IID/evidence-plan")
[ "$C" = "401" ]; check "anonymous cannot read the evidence plan (HTTP 401)" $?
C=$(code "$API/inspections/$IID/evidence-plan" -H "$AUDH")
[ "$C" = "200" ]; check "read-only AUDITOR may view the plan (HTTP 200)" $?
C=$(code -X POST "$API/inspections/$IID/verifications" -H "$AUDH" \
  -H "Content-Type: application/json" -d '{"reason":"auditor must not verify"}')
[ "$C" = "403" ]; check "AUDITOR cannot create verification tasks (HTTP 403)" $?
C=$(code -X POST "$API/inspections/$IID/verifications" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"reason":"no"}')
[ "$C" = "422" ]; check "reason shorter than 3 chars rejected (HTTP 422)" $?

# --- 6. create + start the REQUIRED verification task (checkpoint 4) ------------
T=$(curl -s -X POST "$API/inspections/$IID/verifications" -H "$INSPH" \
  -H "Content-Type: application/json" -d "{
    \"fieldId\": \"$ANCHOR\",
    \"type\": \"MEASUREMENT\",
    \"reason\": \"Weigh the physical contents on a calibrated scale\",
    \"requirementLevel\": \"REQUIRED\"}")
TID=$(jget "$T" "['id']")
[ "$(jget "$T" "['status']")" = "PENDING" ]; check "verification task created PENDING (id ${TID:0:8}…)" $?
C=$(code -X POST "$API/inspections/$IID/verifications" -H "$INSPH" \
  -H "Content-Type: application/json" -d "{\"fieldId\":\"$ANCHOR\",\"type\":\"MEASUREMENT\",\"reason\":\"duplicate open task\"}")
[ "$C" = "409" ]; check "duplicate open task of the same type+anchor rejected (HTTP 409)" $?

S=$(curl -s -X POST "$API/verifications/$TID/start" -H "$INSPH")
[ "$(jget "$S" "['status']")" = "IN_PROGRESS" ]; check "task started → IN_PROGRESS" $?

# --- 7. the DECISION GATE blocks on the open REQUIRED task (checkpoint 7) -------
RS=$(curl -s "$API/inspections/$IID/review-status" -H "$INSPH")
[ "$(jget "$RS" "['verificationTotal']")" = "1" ]; check "review-status counts the verification task" $?
[ "$(jget "$RS" "['verificationOpenRequired']")" = "1" ]; check "review-status shows 1 open REQUIRED task" $?
BLOCKED=$(jget "$RS" "['decisionBlockers'][0]")
contains "$BLOCKED" "Required verification task"; check "decision gate names the required verification task" $?
D=$(curl -s -X POST "$API/inspections/$IID/decision" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"decision":"COMPLIANT"}')
contains "$D" "Required verification task"
check "COMPLIANT decision blocked while the REQUIRED task is open (409)" $?

# --- 8. record the manual measurement (checkpoint 5) -----------------------------
# No instrument verification status supplied → must be recorded as absent,
# never invented as "verified".
M=$(curl -s -X POST "$API/verifications/$TID/result" -H "$INSPH" \
  -H "Content-Type: application/json" -d "{
    \"measuredValue\": 492,
    \"unit\": \"g\",
    \"instrumentId\": \"SCALE-LM-0142\",
    \"notes\": \"average of three weighings\"}")
[ "$(jget "$M" "['status']")" = "COMPLETED" ]; check "measurement recorded → task COMPLETED" $?
echo "$M" | "$PY" -c "
import sys, json
r = json.load(sys.stdin)['results'][0]
assert float(r['measuredValue']) == 492.0, r
assert r['unit'] == 'g', r
assert r['instrumentId'] == 'SCALE-LM-0142', r
assert r.get('instrumentVerificationStatus') is None, r
print('ok')" > /tmp/ui06-meas 2>&1 || true
[ "$(cat /tmp/ui06-meas 2>/dev/null | tail -1)" = "ok" ]
check "measured 492 g stored on the result; instrument status NOT invented (absent)" $?
C=$(code -X POST "$API/verifications/$TID/result" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"measuredValue":500,"unit":"g"}')
[ "$C" = "409" ]; check "second result on a COMPLETED task rejected — append-only (HTTP 409)" $?

# The DECLARED value is untouched; the plan shows both, never a verdict.
FLD=$(curl -s "$API/inspections/$IID/fields" -H "$INSPH")
DECL=$(echo "$FLD" | "$PY" -c "
import sys, json
fs = json.load(sys.stdin)
f = next(x for x in fs if x['id'] == '$ANCHOR')
print(f.get('normalizedValue') or f.get('rawText'))")
[ "$DECL" = "500 g" ]; check "declared value still '500 g' after the measurement (original preserved)" $?
P2=$(curl -s "$API/inspections/$IID/evidence-plan" -H "$INSPH")
echo "$P2" | "$PY" -c "
import sys, json
p = json.load(sys.stdin)
row = next(r for r in p['items'] if r.get('fieldId') == '$ANCHOR' or r.get('findingId') == '$ANCHOR')
assert row['declaredValue'] == '500 g', row['declaredValue']
assert row['status'] == 'VERIFIED', row['status']
lr = row['verification']['latestResult']
assert lr and lr['measuredValue'] == 492, lr
assert not row['gaps'], row['gaps']
assert 'does not evaluate the difference' in row['summary'], row['summary']
print('ok')
" > /tmp/ui06-plan2 2>&1 || true
[ "$(cat /tmp/ui06-plan2 2>/dev/null | tail -1)" = "ok" ]
check "plan: declared 500 beside measured 492, VERIFIED, no open gap, no difference-verdict" $?

# --- 9. the gate opens; the decision is recorded by the human (checkpoint 7) ----
D=$(curl -s -X POST "$API/inspections/$IID/decision" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"decision":"COMPLIANT","reason":"Net quantity verified within permissible error on inspection"}')
contains "$D" "COMPLIANT"; check "COMPLIANT decision recorded once the required evidence exists" $?

# A RECOMMENDED task never blocks (checkpoint 7b).
T2=$(curl -s -X POST "$API/inspections/$IID/verifications" -H "$INSPH" \
  -H "Content-Type: application/json" -d "{
    \"fieldId\": \"$ANCHOR\",
    \"type\": \"MEASUREMENT\",
    \"reason\": \"Re-verification advisory for the record\",
    \"requirementLevel\": \"RECOMMENDED\"}")
T2ID=$(jget "$T2" "['id']")
[ -n "$T2ID" ]; check "RECOMMENDED re-verification task created (open)" $?
D2=$(curl -s -X POST "$API/inspections/$IID/decision" -H "$INSPH" \
  -H "Content-Type: application/json" -d '{"decision":"REQUIRES_FURTHER_REVIEW","reason":"Superseding decision to exercise the RECOMMENDED path"}')
contains "$D2" "REQUIRES_FURTHER_REVIEW"
check "REQUIRES_FURTHER_REVIEW always recordable — RECOMMENDED tasks never block" $?

# --- 10. audit trail: every verification step left an append-only event ---------
A=$(curl -s "$API/inspections/$IID/audit" -H "$INSPH")
echo "$A" | "$PY" -c "
import sys, json
types = {e['eventType'] for e in json.load(sys.stdin)}
need = {'VERIFICATION_CREATED', 'VERIFICATION_STARTED', 'VERIFICATION_RESULT_RECORDED', 'VERIFICATION_COMPLETED', 'DECISION_SUBMITTED'}
missing = need - types
assert not missing, missing
print('ok')
" > /tmp/ui06-audit 2>&1 || true
[ "$(cat /tmp/ui06-audit 2>/dev/null | tail -1)" = "ok" ]
check "audit trail has VERIFICATION_* + DECISION_SUBMITTED events (append-only)" $?

# --- 11. SQLite cross-check: the rows are real, the declaration untouched -------
"$PY" - "$DB" "$TID" "$ANCHOR" <<'EOF' > /tmp/ui06-check 2>&1 || true
import sqlite3, sys

db = sqlite3.connect(sys.argv[1])
tid, fid = (v.replace("-", "") for v in sys.argv[2:4])

task = db.execute(
    "SELECT task_type, requirement_level, status FROM verification_tasks WHERE id = ?",
    (tid,),
).fetchone()
assert task == ("MEASUREMENT", "REQUIRED", "COMPLETED"), task

res = db.execute(
    "SELECT measured_value, unit, instrument_id, instrument_verification_status "
    "FROM verification_results WHERE task_id = ?",
    (tid,),
).fetchall()
assert res == [(492.0, "g", "SCALE-LM-0142", None)], res

# The extracted field the measurement anchors to still carries its ORIGINAL
# declared value — the measurement is stored separately, never merged.
field = db.execute(
    "SELECT normalized_value FROM extracted_fields WHERE id = ?", (fid,)
).fetchone()
assert field and field[0] == "500 g", field

events = [
    e[0]
    for e in db.execute(
        "SELECT event_type FROM audit_events WHERE entity_id = ?", (tid,)
    )
]
for expected in ("VERIFICATION_CREATED", "VERIFICATION_RESULT_RECORDED", "VERIFICATION_COMPLETED"):
    assert expected in events, (expected, events)
print("ok")
EOF
[ "$(cat /tmp/ui06-check 2>/dev/null | tail -1)" = "ok" ]
check "SQLite confirms task/result rows, absent instrument status, untouched declaration" $?

rm -f "$LABEL" "$ROOT/.ui06-photo.jpg" .ui06-anchor .ui06-blocking-findings
echo
echo "UI-06 live e2e: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
