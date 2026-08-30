"""Phase 16 performance benchmark (Prompt 9) — MEASURED, never estimated.

Run against a live API (default http://127.0.0.1:8765) with real images:

    python scripts/benchmark_phase16.py [--base-url http://127.0.0.1:8765]

Measures, via the real HTTP API (the same endpoints the frontend uses):
  1. cold OCR run   — first perception in a fresh server process
                      (PaddleOCR engine init + first inference)
  2. warm OCR run   — engine already cached
  3. evaluation     — deterministic compliance engine over perception evidence
  4. single image end-to-end — create → upload → perceive → evaluate
  5. multi-image end-to-end  — same with three images (three parallel runs)

Every number printed is a wall-clock measurement from time.perf_counter();
nothing is extrapolated or fabricated. CPU-only PaddleOCR means timings are
machine-dependent — record the machine alongside the results.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "db" / "demo_images"
IMAGES = ["demo-food.png", "demo-water.png", "demo-oil.png"]

_TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "REVIEW_REQUIRED"}


def login(base: str) -> dict[str, str]:
    r = requests.post(
        f"{base}/auth/login",
        json={
            "email": "inspector@legalmet.local",
            "password": "changeme-inspector",
        },
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def create_inspection(base: str, headers: dict, name: str) -> str:
    r = requests.post(
        f"{base}/inspections",
        json={"productName": name, "productCategory": "food"},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def upload(base: str, headers: dict, inspection_id: str, filename: str) -> None:
    data = Path(DEMO_DIR / filename).read_bytes()
    r = requests.post(
        f"{base}/inspections/{inspection_id}/images/upload",
        headers=headers,
        files={"file": (filename, data, "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        timeout=120,
    )
    r.raise_for_status()


def perceive_and_wait(base: str, headers: dict, inspection_id: str) -> float:
    """POST /perceive then poll the analysis endpoint until no run is active."""
    t0 = time.perf_counter()
    r = requests.post(
        f"{base}/inspections/{inspection_id}/perceive", headers=headers, timeout=300
    )
    r.raise_for_status()
    while True:
        a = requests.get(
            f"{base}/inspections/{inspection_id}/analysis", headers=headers, timeout=30
        )
        a.raise_for_status()
        body = a.json()
        if body["hasRuns"] and not body["active"]:
            break
        if time.perf_counter() - t0 > 600:  # 10 min hard cap
            raise TimeoutError(f"perception still active after 600s: {body}")
        time.sleep(1.0)
    return time.perf_counter() - t0


def evaluate(base: str, headers: dict, inspection_id: str) -> float:
    t0 = time.perf_counter()
    r = requests.post(
        f"{base}/inspections/{inspection_id}/evaluate", headers=headers, timeout=120
    )
    r.raise_for_status()
    return time.perf_counter() - t0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/api/v1")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    headers = login(base)
    results: list[tuple[str, float]] = []

    # 1. cold OCR (first inference in this server process)
    insp = create_inspection(base, headers, "BENCH-COLD")
    upload(base, headers, insp, IMAGES[0])
    cold = perceive_and_wait(base, headers, insp)
    results.append(("cold OCR run (engine init + first inference)", cold))

    # 2. warm OCR + 3. evaluation
    insp = create_inspection(base, headers, "BENCH-WARM")
    upload(base, headers, insp, IMAGES[0])
    results.append(("warm OCR run (engine cached)", perceive_and_wait(base, headers, insp)))
    results.append(("compliance evaluation", evaluate(base, headers, insp)))

    # 4. single-image end-to-end (fresh inspection, warm engine)
    t0 = time.perf_counter()
    insp = create_inspection(base, headers, "BENCH-FULL")
    upload(base, headers, insp, IMAGES[1])
    perceive_and_wait(base, headers, insp)
    evaluate(base, headers, insp)
    results.append(("single-image end-to-end (create→evaluate, warm)", time.perf_counter() - t0))

    # 5. multi-image end-to-end (three images → three runs)
    t0 = time.perf_counter()
    insp = create_inspection(base, headers, "BENCH-MULTI")
    for name in IMAGES:
        upload(base, headers, insp, name)
    perceive_and_wait(base, headers, insp)
    evaluate(base, headers, insp)
    results.append(("multi-image (3) end-to-end (create→evaluate, warm)", time.perf_counter() - t0))

    print("\n=== Phase 16 measured results (CPU-only, wall clock) ===")
    for label, seconds in results:
        print(f"{label}: {seconds:.1f}s".replace("→", "->"))


if __name__ == "__main__":
    main()
