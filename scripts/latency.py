"""Measure local API scoring latency; requires a running server and sample data."""
import json
import os
import statistics
import time
import uuid

import httpx

SAMPLES = json.loads(open("tests/sample_rows.json", encoding="utf-8").read())
BASE = os.getenv("BASE_URL", "http://localhost:8000")
KEY = os.getenv("ADMIN_API_KEY", "admin-key")

with httpx.Client(base_url=BASE, headers={"X-API-Key": KEY}, timeout=30) as client:
    durations = []
    for i in range(20):
        started = time.perf_counter()
        response = client.post("/transactions", json={
            "idempotency_key": f"latency-{uuid.uuid4().hex}",
            "features": SAMPLES["fraud" if i % 2 else "legit"],
        })
        response.raise_for_status()
        durations.append((time.perf_counter() - started) * 1000)

print(json.dumps({
    "requests": len(durations),
    "mean_ms": round(statistics.mean(durations), 2),
    "p50_ms": round(statistics.median(durations), 2),
    "p95_ms": round(sorted(durations)[int(len(durations) * 0.95) - 1], 2),
}, indent=2))
