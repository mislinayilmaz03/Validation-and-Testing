# Modern Testing Strategy & Prototype — Technical Report

**Course:** SOFT411 Software Validation & Testing, Final International University  
**Assignment:** Lecture 1 — *Principles of Software Testing*, slide 29  
**Feature under test:** split payment — one order total paid with 2–4 instruments
(cards and wallets) in a single request  
**Repository layout:** `app/` service, `tests/` suite, `perf/` k6, `.github/workflows/` CI, `docs/`, `reports/`

---

## 1. Introduction and Scope

The chosen feature is the one from Case Study 1: a payment application lets a customer
pay a single order with several instruments at once. It is small enough to build and
test properly, and it concentrates the risks that make payment software hard — money
must be counted exactly, requests must survive being retried, and a transaction that
spans two external providers can fail halfway through.

A prototype service (~400 lines) was implemented so the tests would have something
real to execute against, rather than being written in the abstract. Everything the
service does is traceable to a risk; nothing was added for completeness.

**In scope:** amount validation and cent distribution, idempotency, sequential capture
with compensation, instrument ownership, feature-flag rollback, latency budget.

**Out of scope:** card tokenisation, 3-D Secure, persistence in a real database, TLS
and secret management, PCI-DSS scope assessment, any user interface.

**Assumptions** (the case statement gives no product rules; stating them is itself a
static-testing activity, and ambiguity is a risk in its own right):

| # | Assumption |
|---|---|
| A1 | A split payment uses at least 2 and at most 4 instruments |
| A2 | Each split is ≥ 1.00 and the order total ≤ 50 000.00 |
| A3 | Amounts have at most 2 decimals; `sum(splits)` must equal `total` to the cent |
| A4 | Card network and wallet service are independent external providers |
| A5 | Every payment request carries an `Idempotency-Key` |
| A6 | The feature can be switched off by configuration without a deployment |
| A7 | A void/refund mechanism exists for compensating a partial charge |

---

## 2. Risk Analysis

Risk score = likelihood × impact (1–5 each). Impact weighs financial loss, regulatory
exposure and, decisively, **reversibility**.

| ID | Risk | How it occurs | L | I | Score | Reversible? |
|----|------|---------------|:-:|:-:|:-----:|---|
| R1 | **Double charge** | user double-clicks, client retries, network drops, webhook delivered twice | 4 | 5 | **20** | No — customer money is taken |
| R2 | **Incorrect totals** | float rounding, undistributed remainder cent, tampered total | 4 | 5 | **20** | No — accounting breaks |
| R3 | **Partial charge** | split 1 captured, split 2 fails, compensation does not run | 4 | 5 | **20** | Partly — needs void/refund |
| R4 | **Timeout / latency** | several provider calls in one request; p95 budget breached | 5 | 3 | **15** | Yes — retry and monitoring |
| R5 | Contract breakage | wallet provider changes schema or error codes | 3 | 4 | 12 | Yes — contract tests |
| R6 | **Regression** | the new path breaks existing single-instrument payments | 3 | 5 | **15** | No — affects all traffic |
| R7 | **Authorisation flaw** | paying with another user's wallet or leaked token | 2 | 5 | **10** | No — security incident |
| R8 | Race condition | parallel duplicates consume the same balance twice | 3 | 4 | 12 | Partly |
| R9 | Rare combinations | mixed currencies, exotic card types | 2 | 2 | 4 | Yes |
| R10 | Accessibility / UI defect | unclear error, keyboard and screen-reader gaps | 3 | 1 | 3 | Yes |

R1, R2 and R3 share the top score, and all three are irreversible — that is why they
drive the strategy. R4 is the most *likely* risk but its impact is recoverable, which
is exactly why it is handled with a threshold and monitoring rather than a hard gate.

---

## 3. Quality Criteria

### 3.1 Functional criteria (must hold for every request)

| # | Criterion | Verified by |
|---|---|---|
| F1 | 2–4 splits; anything else is rejected before any capture | TC01–TC04 |
| F2 | Each split ≥ 1.00; zero, negative and over-precise amounts rejected | TC05–TC07, TC10b |
| F3 | Order total ≤ 50 000.00 | TC08 |
| F4 | `sum(splits) == total` to the cent, and an indivisible total loses no cent | TC09, TC10, TC22 |
| F5 | **Atomicity:** either all splits are captured, or none remain captured | TC09, TC14–TC16b |
| F6 | **Idempotency:** a replayed request never charges twice | TC11–TC13b |
| F7 | Every instrument must belong to the authenticated caller | TC17–TC19 |
| F8 | A failed compensation is queued for a human and raises an alert | TC16 |
| F9 | Payment state is observable afterwards (`PAID` / `FAILED` with cause) | TC20, TC20b |

### 3.2 Non-functional criteria

| # | Attribute | Target | Verified by |
|---|---|---|---|
| N1 | Performance | p95 < 15 ms application latency; p95 < 2.5 s end-to-end in a real environment | `test_performance_smoke.py`, `perf/k6-split-smoke.js` |
| N2 | Security | no medium/high SAST finding; all abuse cases rejected with no money moved | Bandit, TC17–TC19b |
| N3 | Reliability | no provider failure leaves money captured; failed compensation is never silent | TC14–TC16b |
| N4 | Observability | captures are queryable per order; manual queue and alerts are inspectable | audit endpoints used by the tests |
| N5 | Operability | the feature can be switched off in under a minute without a deployment | TC21 |
| N6 | Maintainability | the suite runs in ~1 s so it can gate every commit | CI timing |
| N7 | Accessibility | **not assessed** — the prototype has no UI | documented gap |

---

## 4. Test Strategy

The strategy follows the lecture's risk-based reasoning: effort is proportional to
*irreversibility*, not to the size of the component.

**Level choice.** Almost all checks sit at the unit and API level. Money arithmetic is
verified in isolation (fast, exhaustive-ish via property-based testing), and behaviour
is verified through the HTTP boundary where the rules actually live. There is no
end-to-end UI layer because there is no UI; in the full product this is where three
targeted Playwright journeys would sit.

**Techniques applied** (detail in `docs/TEST-CASES.md`): boundary-value analysis,
equivalence partitioning, decision rules, state-transition testing, concurrency
testing, fault injection, abuse-case testing, property-based testing and a
threshold-gated performance smoke test.

**Oracles are side effects, not status codes.** Every negative case asserts through the
audit endpoint that zero captures exist. A `403` that still moved money would satisfy a
status-only assertion, so the assertion was designed around the invariant instead.

**What is deliberately not automated.** R9 (rare multi-currency combinations) and R10
(accessibility) have no automated coverage. They are low impact, cheap to detect in
production, and expensive to simulate; they are accepted behind a feature flag with
monitoring. Recording that decision is part of the strategy — an untested area that
nobody wrote down is a blind spot, while one that is written down is a managed risk.

---

## 5. Automation and the CI/CD Pipeline

`.github/workflows/ci.yml` runs on every push, pull request and manual dispatch:

| Stage | Step | Gate |
|---|---|---|
| 1 | Bandit SAST on `app/` | fails on medium/high severity |
| 2 | `pytest -m "not performance"` — boundary, idempotency, compensation, security, state | **blocking**, any failure stops the pipeline |
| 3 | `pytest -m performance` — p95 latency budget | **blocking** on threshold breach |
| 4 | Upload `test-report.html`, `junit.xml`, `bandit.txt`, `performance-smoke.json` | evidence artefact, runs even on failure |
| 5 | Write the pass/fail counts into the GitHub step summary | visible without opening artefacts |

Fast checks run first so feedback arrives in seconds. The whole gate completes in a few
seconds locally, which is what makes it acceptable on every commit — a gate that is
slow or flaky gets bypassed, and then it protects nothing.

---

## 6. Results and Evidence

All artefacts are committed under `reports/`.

| Evidence | Result | File |
|---|---|---|
| Functional and security suite | **34 passed, 0 failed** in 1.11 s | `junit.xml`, `test-report.html`, `pytest-console.txt` |
| Static security scan | **0 findings** at any severity after triage (4 low-severity false positives suppressed per line with justification) | `bandit.txt`, `bandit-full.txt`, `docs/SECURITY-TRIAGE.md` |
| Performance smoke | mean 0.60 ms, p50 0.58 ms, **p95 0.77 ms** vs a 15 ms budget | `performance-smoke.json` |
| Defect injection | **3 of 3 injected defects caught — 100 %** | `defect-injection.json` |

The defect-injection result is the most informative number here. A green suite only
proves that the tests passed; injecting a real defect and watching the right tests fail
is what demonstrates defect-finding power:

| Mutant | Injected defect | Outcome |
|---|---|---|
| M1 | idempotency lookup always misses | caught — TC11, TC12, TC13 fail |
| M2 | `sum(splits) == total` check removed | caught — TC09 (both variants), TC19 fail |
| M3 | compensation disabled | caught — TC14, TC15, TC15b, TC16, TC16b fail |

---

## 6.1 What Went Wrong While Testing

The green suite is the least informative part of this project. Seven mistakes were made
and corrected along the way; none of them was an application crash, and every one of
them was about the **quality of the evidence** the suite produces. They are recorded
here because they are the part with transferable value.

| # | Mistake | Root cause | Correction | Lesson |
|---|---------|-----------|-----------|--------|
| 1 | The concurrency case failed, and the **test** was wrong — it demanded `409` from all seven losers of the race, while the service returned one `201` and seven `200` replays | The assertion was tied to status codes, but rejecting an in-flight duplicate and replaying the stored response are equally safe | Asserted the invariant instead: exactly two captures per order; status may be `200` or `409` and a replay must return the same `payment_id` | Automation executes an oracle, it does not supply one. No tool could say which expectation was correct |
| 2 | All 34 checks passed on the first complete run, which was reassuring and uninformative | The suite had only ever run against correct code, and a weak assertion passes exactly like a strong one | Wrote `tools/defect_injection.py` and injected three defects matching R1, R2 and R3 | A passing suite is a claim; a defect that the right tests catch is evidence |
| 3 | The first injected defect failed 16 tests across unrelated files instead of the 3 it targeted | The patch left the idempotency record in an in-flight state, so a later call raised `KeyError` — a crash was injected, not the defect under study | Moved the mutation one level down, into the lookup in `store.begin()` | A defect experiment is only useful if the blast radius is small enough to read |
| 4 | The injection script reported an empty summary, and once mistook a `FAILED ...` line for the result | pytest's console output was being scraped with a regex; line order on Windows was not what the script assumed | Read `reports/junit.xml` instead — the machine-readable report pytest already writes | If a tool offers machine-readable output, measure from that, not from text written for humans |
| 5 | The performance threshold was set at 60 ms while the measured p95 was 0.77 ms, so the check could never fail | The number was chosen before any measurement, "to be safe" | Measured first, then set the budget at 15 ms (~15× the observed value) | A threshold is a sensitivity/flakiness trade-off and cannot be chosen honestly without data |
| 6 | Bandit raised four false "hardcoded password" findings, and the first suppression comment made it emit warnings on every run | The strings are fault-injection selectors in the mock; the justification had been written on the same line as `# nosec`, so Bandit parsed it as rule names | Per-line `# nosec B105` with the reason on the preceding line, triage written up in `docs/SECURITY-TRIAGE.md`, CI gate set to medium severity | Skipping the rule project-wide would also hide a real secret committed later; triage means deciding with a reason you can show |
| 7 | Installing the dependencies globally downgraded `starlette`/`uvicorn` and broke an unrelated project on the same machine; the CI file also carried a flag for a pytest plugin that was never installed | `pip install` was run without an isolated environment, and a command line was copied without checking it against `requirements.txt` | Created a project `.venv`, restored the global versions, pinned every dependency, removed the invalid flag | Test results are only as trustworthy as the environment: an unpinned shared environment means green locally and red in CI with no way to say which was right |

Grouped by what they have in common:

- **The oracle is human** (1, 5) — a tool can run a check, but deciding the correct
  answer and an honest threshold stayed a human responsibility.
- **Signal beats drama** (2, 3, 4) — a green suite, a 16-test failure and a scraped log
  line all look like information and carry almost none.
- **Context is part of the test** (6, 7) — a finding needs triage and an environment
  needs pinning, or the result is neither reproducible nor trustworthy.

---

## 7. Residual Risk and Release Recommendation

| Risk | Status | Mitigation |
|---|---|---|
| R1, R2, R3, R6, R7, R8 | covered by blocking tests | gate on every commit |
| R4 | partially covered | application-level budget in CI; k6 against staging; p95/timeout dashboard and alerts in production |
| R5 | **not covered** — the providers are mocked | consumer-driven contract tests (Pact) before a real integration |
| R9, R10 | **not covered** by design | flag-disabled at first, segment error rates monitored, accessibility audit scheduled when a UI exists |

**Recommendation:** *conditional go* — release behind `SPLIT_PAYMENT_ENABLED` with a 1 %
canary, automatic rollback if the payment success rate drops more than 2 % below
baseline or p95 exceeds 3 s, and an hourly reconciliation job watching for duplicate
captures with zero tolerance.

Mapping to the lecture's principles: the evidence above reports residual risk rather
than claiming correctness (principle 1), coverage was chosen by risk because exhaustive
testing is impossible (principles 2 and 4), the cheapest checks run first and earliest
(principle 3), property-based testing and defect injection keep the suite from ageing
into a ritual (principle 5), the irreversibility of money defines what blocks a release
in this domain (principle 6), and the untested accessibility and usability gaps are
recorded because a technically correct payment can still fail its users (principle 7).

The 629-word reflection in `docs/REFLECTION.md` discusses what automation missed and
where human judgement remained necessary.
