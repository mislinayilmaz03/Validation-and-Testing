"""TC23: the performance check required by the assignment.

Technique: a performance smoke test with an explicit threshold. It measures
application-level latency only (in-process client, mocked providers), so it
guards against an algorithmic regression - not against production capacity.
The k6 script in perf/ is the counterpart that runs against a real
environment; see the reflection for why the difference matters.
"""
import json
import statistics
import time
import uuid
from pathlib import Path

import pytest

from conftest import ENDPOINT, USER, split_body

REQUESTS = 200
# Observed locally: mean ~0.6 ms, p95 ~0.8 ms. The budget is set roughly 15x
# above that: tight enough to catch an algorithmic regression (an O(n^2) loop
# or a per-split full scan), loose enough not to turn a slower CI runner into
# a flaky failure. A gate that fails randomly destroys trust in the pipeline.
P95_BUDGET_MS = 15.0
MEAN_BUDGET_MS = 10.0
REPORT = Path(__file__).resolve().parents[1] / "reports" / "performance-smoke.json"


@pytest.mark.performance
@pytest.mark.tc("TC23")
def test_split_payment_latency_budget(client):
    durations = []
    for i in range(REQUESTS):
        body = split_body(f"ord_perf_{i}", splits=[
            {"instrument": "card", "token": "tok_load", "amount": "60.00"},
            {"instrument": "wallet", "wallet_id": "w_load", "amount": "40.00"},
        ])
        headers = {"X-User-Id": USER, "Idempotency-Key": str(uuid.uuid4())}

        started = time.perf_counter()
        resp = client.post(ENDPOINT, json=body, headers=headers)
        durations.append((time.perf_counter() - started) * 1000)

        assert resp.status_code == 201

    durations.sort()
    result = {
        "requests": REQUESTS,
        "mean_ms": round(statistics.mean(durations), 2),
        "p50_ms": round(durations[int(REQUESTS * 0.50)], 2),
        "p95_ms": round(durations[int(REQUESTS * 0.95)], 2),
        "p99_ms": round(durations[int(REQUESTS * 0.99)], 2),
        "max_ms": round(durations[-1], 2),
        "p95_budget_ms": P95_BUDGET_MS,
        "scope": "application layer, mocked providers, in-process client",
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("\nperformance smoke:", json.dumps(result))

    assert result["p95_ms"] < P95_BUDGET_MS, f"p95 budget exceeded: {result}"
    assert result["mean_ms"] < MEAN_BUDGET_MS, f"mean budget exceeded: {result}"
