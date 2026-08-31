"""Golden demo-flow walkthrough + failure-resilience check (Prompt 10).

Drives the LIVE HTTP API exactly the way the UI does, timing each stage of the
judge demo flow (Prompt 10, Phase 4/6) and then deliberately breaking things
(Prompt 10, Phase 5) to verify the system fails honestly — never fabricating
output, never converting an error into a pass.

Run from ``services/api`` with the backend already running on :8000:

    .venv/Scripts/python.exe scripts/walkthrough_p10.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

import os
BASE = os.environ.get("PERF_BASE_URL", "http://localhost:8000/api/v1")
HERE = Path(__file__).resolve().parent
LABEL = HERE.parent / "tests" / "dataset" / "images" / "food-clean-001.png"
DEMO_IMAGE = HERE.parent / "app" / "db" / "demo_images" / "demo-food.png"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def login(email: str, password: str) -> dict:
    r = requests.post(
        f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def main() -> None:
    print("=" * 72)
    print("PROMPT 10 — GOLDEN DEMO FLOW (timed) + FAILURE RESILIENCE")
    print("=" * 72)

    # ---- STEP 1-2: login, the seeded demo set -----------------------------
    t0 = time.perf_counter()
    inspector = login("inspector@legalmet.local", "changeme-inspector")
    check("login", True, f"{time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    inspections = requests.get(f"{BASE}/inspections", headers=inspector, timeout=30).json()
    refs = [i["referenceNo"] for i in inspections["items"]]
    check(
        "seeded demo set",
        {"DEMO-FOOD", "DEMO-WATER", "DEMO-OIL", "DEMO-QUINOA"} <= set(refs),
        f"{refs} ({time.perf_counter() - t0:.2f}s)",
    )

    # ---- STEP 3: create a new inspection ----------------------------------
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/inspections",
        headers=inspector,
        json={
            "productName": "SUNRISE Crunchy Masala (live demo)",
            "productCategory": "food",
            "note": "Prompt 10 golden-flow walkthrough",
        },
        timeout=30,
    )
    check("create inspection", r.status_code == 201, f"{time.perf_counter() - t0:.2f}s")
    inspection_id = r.json()["id"]

    # ---- STEP 4: upload a package image -----------------------------------
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/images/upload",
        headers=inspector,
        files={"file": ("food-clean-001.png", LABEL.read_bytes(), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=120,
    )
    check("upload image", r.status_code == 201, f"{time.perf_counter() - t0:.2f}s")

    # ---- STEP 5: start perception (real OCR) ------------------------------
    t0 = time.perf_counter()
    r = requests.post(f"{BASE}/inspections/{inspection_id}/perceive", headers=inspector, timeout=60)
    check("start perception (202)", r.status_code == 202, f"{time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    deadline = time.monotonic() + 240
    while True:
        a = requests.get(
            f"{BASE}/inspections/{inspection_id}/analysis", headers=inspector, timeout=120
        ).json()
        if not a.get("active") and a.get("hasRuns"):
            break
        if time.monotonic() > deadline:
            raise SystemExit("perception did not finish in 240s")
        time.sleep(2)
    ocr_seconds = time.perf_counter() - t0
    check("perception (real OCR) completed", True, f"{ocr_seconds:.1f}s")

    # ---- STEP 6: extracted fields + confidence ----------------------------
    fields = requests.get(
        f"{BASE}/inspections/{inspection_id}/fields", headers=inspector, timeout=30
    ).json()
    detected = [f for f in fields if f["status"] == "DETECTED"]
    review = [f for f in fields if f["status"] == "REVIEW_REQUIRED"]
    check(
        "fields extracted with statuses",
        len(detected) >= 4 and len(fields) > len(detected),
        f"{len(detected)} DETECTED, {len(review)} REVIEW_REQUIRED, {len(fields)} total",
    )
    print(
        "        sample:",
        ", ".join(
            f'{f["fieldType"]}={f["normalizedValue"]} ({f["confidence"]:.2f})'
            for f in fields[:4]
        ),
    )

    # ---- STEP 7-9: evaluate + evidence chain + version context ------------
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/evaluate", headers=inspector, timeout=120
    )
    check("deterministic evaluation", r.status_code == 200, f"{time.perf_counter() - t0:.2f}s")
    evaluation_id = r.json()["evaluation"]["id"]

    findings = requests.get(
        f"{BASE}/inspections/{inspection_id}/compliance/findings", headers=inspector, timeout=30
    ).json()
    statuses = {}
    for f in findings:
        statuses[f["status"]] = statuses.get(f["status"], 0) + 1
    check(
        "findings produced (no verdict without evidence)",
        len(findings) >= 8 and "NON_COMPLIANT" in statuses,
        f"{len(findings)} findings: {statuses}",
    )

    # evidence chain + version context on one NON_COMPLIANT finding
    nc = next((f for f in findings if f["status"] == "NON_COMPLIANT"), findings[0])
    explanation = nc.get("explanation") or ""
    check(
        "finding explanation carries version context",
        "version" in explanation and "in force" in explanation,
        explanation[:110].replace("\n", " "),
    )
    graph = requests.get(
        f"{BASE}/compliance/findings/{nc['id']}/evidence-graph", headers=inspector, timeout=30
    )
    check(
        "evidence graph traces finding to image",
        graph.status_code == 200 and graph.json().get("nodes"),
        f"{len(graph.json().get('nodes', []))} nodes",
    )

    # ---- STEP 10: honest states present ------------------------------------
    all_status_values = set(statuses) | {f["status"] for f in fields}
    honest_states = {"NOT_DETECTED", "REVIEW_REQUIRED", "NOT_APPLICABLE"} & all_status_values
    check(
        "honest states shown (not just pass/fail)",
        len(honest_states) >= 2,
        f"states present: {sorted(honest_states)}",
    )

    # ---- STEP 11: inspector review ------------------------------------------
    # decision gate FIRST: COMPLIANT must be blocked while the MAJOR finding is
    # unresolved. After the inspector CONFIRMs it (a human verdict exists), the
    # gate deliberately opens — the inspector has final authority (Prompt 7
    # semantics, covered by test_hitl.py test_gate_opens_after_resolution).
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/decision",
        headers=inspector,
        json={"decision": "COMPLIANT", "reason": "gate test", "evaluationId": evaluation_id},
        timeout=30,
    )
    check(
        "decision gate blocks COMPLIANT while finding unresolved",
        r.status_code in (409, 400),
        f"HTTP {r.status_code}",
    )

    r = requests.post(
        f"{BASE}/compliance/findings/{nc['id']}/review",
        headers=inspector,
        json={"action": "CONFIRM", "reason": "Prompt 10 walkthrough confirmation"},
        timeout=30,
    )
    check("inspector review (CONFIRM)", r.status_code == 200, f"{time.perf_counter() - t0:.2f}s")

    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/decision",
        headers=inspector,
        json={
            "decision": "REQUIRES_FURTHER_REVIEW",
            "reason": "Prompt 10 walkthrough — honest pending state",
            "evaluationId": evaluation_id,
        },
        timeout=30,
    )
    check("inspector decision recorded", r.status_code == 200, r.json().get("decision", ""))

    # ---- STEP 12-13: audit trail + evaluation report ------------------------
    audit = requests.get(
        f"{BASE}/inspections/{inspection_id}/audit", headers=inspector, timeout=30
    ).json()
    check("audit trail complete", len(audit) >= 8, f"{len(audit)} events")
    ev = requests.get(
        f"{BASE}/compliance/evaluations/{evaluation_id}", headers=inspector, timeout=30
    )
    check("evaluation report retrievable", ev.status_code == 200, ev.json()["status"])

    # ---- STEP 14: analytics endpoints ---------------------------------------
    dash = requests.get(f"{BASE}/analytics/dashboard", headers=inspector, timeout=30)
    check("dashboard analytics reachable", dash.status_code == 200, "")

    print()
    print("=" * 72)
    print("FAILURE RESILIENCE (Phase 5) — must fail honestly, never fake a pass")
    print("=" * 72)

    # garbage bytes pretending to be an image
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/images/upload",
        headers=inspector,
        files={"file": ("label.png", b"this is not an image at all" * 100, "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=30,
    )
    code = r.json().get("error", {}).get("code", "")
    check("garbage image rejected", r.status_code >= 400, f"HTTP {r.status_code} {code}")

    # not-an-image content type
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/images/upload",
        headers=inspector,
        files={"file": ("notes.txt", b"plain text file", "text/plain")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=30,
    )
    check("non-image upload rejected", r.status_code >= 400, f"HTTP {r.status_code}")

    # blurred/unusable image → quality gate
    blur = HERE.parent / "tests" / "dataset" / "images" / "food-blur-011.png"
    r = requests.post(
        f"{BASE}/inspections/{inspection_id}/images/upload",
        headers=inspector,
        files={"file": ("blur.png", blur.read_bytes(), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=30,
    )
    grade = r.json().get("qualityGrade") if r.status_code == 201 else None
    check(
        "blurry image graded honestly (gate or low grade)",
        r.status_code >= 400 or grade in ("POOR", "REJECTED", "REVIEW_REQUIRED"),
        f"HTTP {r.status_code} grade={grade}",
    )

    # perception on an inspection with no images
    r = requests.post(
        f"{BASE}/inspections",
        headers=inspector,
        json={"productName": "Empty inspection", "productCategory": "food"},
        timeout=30,
    )
    empty_id = r.json()["id"]
    r = requests.post(f"{BASE}/inspections/{empty_id}/perceive", headers=inspector, timeout=30)
    code = r.json().get("error", {}).get("code", "")
    check(
        "perception without images fails honestly",
        r.status_code >= 400,
        f"HTTP {r.status_code} {code}",
    )

    # evaluation before perception
    r = requests.post(f"{BASE}/inspections/{empty_id}/evaluate", headers=inspector, timeout=30)
    check("evaluation without perception handled", r.status_code in (200, 400, 409),
          f"HTTP {r.status_code}")

    # malformed JSON body
    r = requests.post(
        f"{BASE}/inspections",
        headers=inspector,
        data="{not json",
        timeout=30,
    )
    check("malformed body rejected", r.status_code == 422, f"HTTP {r.status_code}")

    # nonexistent inspection
    r = requests.get(
        f"{BASE}/inspections/00000000-0000-0000-0000-000000000000",
        headers=inspector,
        timeout=30,
    )
    check("nonexistent inspection → 404", r.status_code == 404, f"HTTP {r.status_code}")

    # anonymous write rejected
    r = requests.post(
        f"{BASE}/inspections",
        json={"productName": "anon", "productCategory": "food"},
        timeout=30,
    )
    check("anonymous write rejected", r.status_code == 401, f"HTTP {r.status_code}")

    # read-only auditor cannot write
    auditor = login("auditor@legalmet.local", "changeme-inspector")
    r = requests.post(
        f"{BASE}/inspections",
        headers=auditor,
        json={"productName": "auditor attempt", "productCategory": "food"},
        timeout=30,
    )
    check("auditor write rejected (403)", r.status_code == 403, f"HTTP {r.status_code}")

    # report generation for the walkthrough inspection
    r = requests.get(f"{BASE}/inspections/{inspection_id}", headers=inspector, timeout=30)
    check("inspection detail (report source) retrievable", r.status_code == 200, "")

    print()
    print("=" * 72)
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
    print("=" * 72)
    summary = {"passed": len(PASS), "failed": len(FAIL), "failures": FAIL,
               "ocr_seconds": round(ocr_seconds, 1)}
    (HERE / "walkthrough_p10_result.json").write_text(json.dumps(summary, indent=2))
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
