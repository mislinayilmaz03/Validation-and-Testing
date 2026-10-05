# Modern Testing Strategy & Prototype
## Split Payment across Cards and Wallets

**Course:** SOFT411 — Software Validation & Testing  
**Institution:** Final International University  
**Instructor:** Asst. Prof. Dr. Ibrahim Adeshola  
**Assignment:** Lecture 1 — *Principles of Software Testing*, slide 29  
**Student:** Buğra Kor  
**Submission date:** 3 October 2026

---

### Deliverable checklist

| Assignment requirement | Delivered | Where |
|---|---|---|
| A small web/mobile/API system or a clearly defined feature | FastAPI split payment service, ~400 lines | `app/` |
| Short risk analysis | 10 risks scored by likelihood × impact × reversibility | Technical report §2 |
| Functional + non-functional quality criteria | 9 functional (F1–F9), 7 non-functional (N1–N7) | Technical report §3 |
| At least **12** test cases using test design techniques | **23 designed**, 10 techniques, all automated | Test case design document |
| At least **4** automated checks | **34 executed pytest cases, all passing** | `tests/` |
| One CI/CD workflow that runs on change | GitHub Actions, 5 stages, blocking gates | `.github/workflows/ci.yml` |
| One security / performance / accessibility check | **Security** (Bandit SAST + 5 abuse cases) **and performance** (p95 budget + k6) | Security triage document, `perf/` |
| 500–700 word reflection | **629 words** | Reflection document |
| Evidence: repository, test report, screenshots | Repository link, HTML + JUnit reports, Bandit report, performance JSON, defect-injection JSON, 6 screenshots | Evidence section, `reports/` |

### Results at a glance

| Measurement | Result |
|---|---|
| Automated test cases | **34 passed, 0 failed** (1.11 s) |
| Static security scan (Bandit) | **0 findings** at any severity after documented triage |
| Performance smoke | mean 0.60 ms, **p95 0.77 ms** against a 15 ms budget |
| Defect injection (mutation-style) | **3 of 3 injected defects caught — 100 %** |
| Risks covered by blocking tests | R1, R2, R3, R6, R7, R8 |
| Risks consciously deferred to monitoring | R4 (partly), R5, R9, R10 |

> **Note on the results above:** "34 of 34 passed" is the least informative number in
> this report. Section 6.1 documents the **seven mistakes** made while building the
> suite — including one case where the test was wrong and the application was right —
> because that is where the learning is.

### Contents

1. Repository, test report and evidence — repository link, result summary, artefact index, screenshots
2. Technical report — scope, risk analysis, quality criteria, strategy, CI/CD, results, **what went wrong (§6.1)**, release recommendation
3. Test case design and traceability — 23 cases mapped to techniques and risks, plus defect-injection evidence
4. Security check and finding triage — SAST policy, abuse cases, explicit gaps
5. Reflection — what automation missed and where human judgement was necessary

<!--PAGEBREAK-->
