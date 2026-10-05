# Split Payment — Modern Testing Strategy & Prototype

SOFT411 Software Validation & Testing — Assignment (Lecture 1, slide 29)
Feature under test: **split payment** — one order total paid with 2–4 instruments
(cards and wallets) in a single request, based on Case Study 1.

## What is in here

| Assignment requirement | Where it is satisfied |
|---|---|
| A small system or clearly defined feature | `app/` — a FastAPI split payment service (401 lines) |
| Short risk analysis + functional and non-functional quality criteria | `docs/TECHNICAL-REPORT.md` §2–§4 |
| At least 12 test cases using test design techniques | `docs/TEST-CASES.md` — **23 designed**, all automated (34 executed cases) |
| At least 4 automated checks | `tests/` — **34 passing** pytest cases |
| One CI/CD workflow that runs on change | `.github/workflows/ci.yml` |
| One security / performance / accessibility check | **Both**: Bandit SAST + 5 abuse-case tests (`docs/SECURITY-TRIAGE.md`) and a p95 latency budget (`tests/test_performance_smoke.py`, `perf/k6-split-smoke.js`) |
| 500–700 word reflection | `docs/REFLECTION.md` (629 words) |
| Test report / evidence | `docs/EVIDENCE.md` + `reports/` — HTML report, JUnit XML, Bandit report, performance JSON, defect-injection JSON, screenshots |

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt     # Linux/macOS: .venv/bin/python

# full suite with an HTML report
.venv/Scripts/python.exe -m pytest --html=reports/test-report.html --self-contained-html

# only the blocking functional checks (what the CI gate runs first)
.venv/Scripts/python.exe -m pytest -m "not performance"

# only the security abuse cases / only the performance budget
.venv/Scripts/python.exe -m pytest -m security
.venv/Scripts/python.exe -m pytest -m performance

# static security scan
.venv/Scripts/python.exe -m bandit -r app -c bandit.yaml --severity-level medium

# does the suite actually catch defects? inject three and find out
.venv/Scripts/python.exe tools/defect_injection.py

# run the service and explore the API
.venv/Scripts/python.exe -m uvicorn app.main:app --reload    # http://localhost:8000/docs
```

Rebuilding the submitted document (needs the report tooling, not required for the tests):

```bash
.venv/Scripts/python.exe -m pip install -r requirements-report.txt
.venv/Scripts/python.exe -m playwright install chromium

.venv/Scripts/python.exe tools/make_screenshots.py    # reports/screenshots/*.png from the artefacts
.venv/Scripts/python.exe tools/build_submission.py    # docs/*.md -> reports/SOFT411-Split-Payment-Report.pdf
```

## Current results

```
34 passed in 1.11s                     pytest (reports/junit.xml)
0 findings at any severity             bandit (reports/bandit.txt)
p95 0.77 ms / budget 15 ms             performance smoke (reports/performance-smoke.json)
3 of 3 injected defects caught (100%)  defect injection (reports/defect-injection.json)
```

## The feature in one request

```http
POST /v1/payments/split
X-User-Id: user_1
Idempotency-Key: 7c1f...            <- replay protection (risk R1)
Content-Type: application/json

{
  "order_id": "ord_1001",
  "currency": "TRY",
  "total": "100.00",                 <- strings, never JSON floats (risk R2)
  "splits": [
    {"instrument": "card",   "token": "tok_ok",  "amount": "60.00"},
    {"instrument": "wallet", "wallet_id": "w_main", "amount": "40.00"}
  ]
}
```

Rules enforced: 2–4 splits, each split ≥ 1.00, total ≤ 50 000.00, amounts with at most
two decimals, and `sum(splits) == total` to the cent. If any split fails at the
provider, the already captured splits are compensated (void/refund) so the order is
never left half paid; if the compensation itself fails the case is queued for manual
intervention and an alert is raised.

## Design decisions that exist because of the risks

| Decision | Risk it addresses |
|---|---|
| `Decimal` everywhere, amounts accepted as strings, JSON floats refused | R2 incorrect totals |
| Mandatory `Idempotency-Key` with an in-flight marker and a body fingerprint | R1 double charge, R8 race condition |
| Sequential capture with compensation on failure, plus a manual queue | R3 partial charge |
| Instrument ownership checked against the caller before any capture | R7 authorisation |
| `SPLIT_PAYMENT_ENABLED` feature flag, verified by a test | rollback / R6 regression |
| `GET /v1/orders/{id}/captures` audit endpoint | makes "no double charge" assertable |

## Layout

```
app/        money.py (decimal arithmetic), psp.py (mock providers + fault injection),
            store.py (idempotency + captures), main.py (API)
tests/      boundary values, idempotency, compensation, security, state/flag,
            property-based, performance smoke
perf/       k6-split-smoke.js  (threshold-gated load test for a real environment)
tools/      defect_injection.py (lightweight mutation testing),
            make_screenshots.py + build_submission.py (submission document)
docs/       COVER.md, EVIDENCE.md, TECHNICAL-REPORT.md, TEST-CASES.md,
            SECURITY-TRIAGE.md, REFLECTION.md
reports/    generated evidence (committed so the submission is self-contained),
            screenshots/, SOFT411-Split-Payment-Report.pdf (the submitted document)
```

## Scope and honesty notes

- The providers are **mocked**. A real card network cannot be asked to decline or time
  out on demand, and deterministic tests are worth more than realistic flaky ones.
- The performance smoke test runs **in-process against mocks**, so it measures
  application overhead only — it is a regression detector, not a capacity test. The k6
  script is its counterpart for a deployed environment.
- Persistence is **in-memory**. The structures model the unique constraints a database
  would enforce, which is what the idempotency tests assert against.
- Risks R9 (rare multi-currency combinations) and R10 (accessibility) are **not tested**
  and are consciously deferred to post-deployment monitoring; the reasoning is in the
  reflection.
