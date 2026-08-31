"""Phase 16 (Prompt 11) — three REAL perception runs, per-stage timings.

Run against a live, freshly-booted, prewarmed API server:

    python scripts/perf_three_runs.py [--base-url http://127.0.0.1:8916/api/v1]

Three fresh inspections, each with one real package image, each perceived
through the real HTTP API. After each run completes, the processing-run row's
measured stage timings (persisted by the backend) are read back and printed.

Every number printed is a wall-clock or backend-recorded measurement;
nothing is extrapolated or fabricated.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "db" / "demo_images"
IMAGES = ["demo-food.png", "demo-water.png", "demo-oil.png"]


def login(base: str) -> dict[str, str]:
    r = requests.post(
        f"{base}/auth/login",
        json={"email": "inspector@legalmet.local", "password": "changeme-inspector"},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def create_inspection(base: str, headers: dict[str, str], name: str) -> str:
    r = requests.post(
        f"{base}/inspections",
        json={"productName": name, "productCategory": "food"},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def upload(base: str, headers: dict[str, str], inspection_id: str, filename: str) -> None:
    data = (DEMO_DIR / filename).read_bytes()
    r = requests.post(
        f"{base}/inspections/{inspection_id}/images/upload",
        headers=headers,
        files={"file": (filename, data, "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=120,
    )
    r.raise_for_status()


def perceive_and_wait(base: str, headers: dict[str, str], inspection_id: str) -> float:
    t0 = time.perf_counter()
    r = requests.post(f"{base}/inspections/{inspection_id}/perceive", headers=headers, timeout=600)
    r.raise_for_status()
    while True:
        a = requests.get(
            f"{base}/inspections/{inspection_id}/analysis", headers=headers, timeout=30
        )
        a.raise_for_status()
        body = a.json()
        if body["hasRuns"] and not body["active"]:
            break
        if time.perf_counter() - t0 > 600:
            raise TimeoutError(f"perception still active after 600s: {body}")
        time.sleep(0.5)
    return time.perf_counter() - t0


def run_stages(base: str, headers: dict[str, str], inspection_id: str) -> dict:
    """Read the processing-run row's recorded summary (stage timings)."""
    r = requests.get(
        f"{base}/inspections/{inspection_id}/processing", headers=headers, timeout=30
    )
    r.raise_for_status()
    runs = r.json()
    if isinstance(runs, dict):
        runs = runs.get("items", [])
    for run in runs:
        if run.get("status") in {"COMPLETED", "PARTIAL", "REVIEW_REQUIRED"}:
            return run
    return runs[0] if runs else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8916/api/v1")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    headers = login(base)
    timings: list[tuple[str, float]] = []

    for i, image in enumerate(IMAGES, start=1):
        insp = create_inspection(base, headers, f"PERF16-{i}")
        upload(base, headers, insp, image)
        elapsed = perceive_and_wait(base, headers, insp)
        timings.append((f"run {i} ({image})", elapsed))
        run = run_stages(base, headers, insp)
        summary = run.get("summary") or {}
        print(f"\n--- run {i}: {image} ---")
        print(f"wall clock: {elapsed:.1f}s")
        print(f"status: {run.get('status')}")
        print(f"duration_ms (backend): {run.get('durationMs')}")
        if isinstance(summary, dict):
            for key in sorted(summary):
                if key.endswith(("Ms", "ms")) or "time" in key.lower():
                    print(f"{key}: {summary[key]}")
        else:
            print(f"summary: {json.dumps(summary)[:400]}")

    print("\n=== Phase 16: three measured perception runs (prewarmed server) ===")
    for label, seconds in timings:
        print(f"{label}: {seconds:.1f}s")


if __name__ == "__main__":
    main()
