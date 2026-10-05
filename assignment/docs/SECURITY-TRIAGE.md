# Security Check and Finding Triage

The assignment requires at least one security, performance or accessibility check.
This project includes **two security layers** plus a performance check.

## 1. Static analysis (SAST) — Bandit

```
bandit -r app -c bandit.yaml -f txt -o reports/bandit.txt --severity-level medium
```

**Gate policy:** the CI step fails on *medium* and *high* severity findings. Low
severity findings are still written to the report and triaged here. A gate that
blocks on known false positives is abandoned by the team within a week, which is
worse than a gate that is honest about what it enforces.

### Findings and triage

| ID | Finding | Location | Severity | Decision |
|----|---------|----------|----------|----------|
| B105 ×4 | "Possible hardcoded password" on `tok_declined`, `tok_timeout`, `tok_provider_error`, `tok_void_fails` | `app/psp.py` | Low (Medium confidence) | **False positive — suppressed per line with `# nosec B105`.** These string literals are fault-injection selectors inside the *mock* provider, not credentials. A real PSP client would hold no tokens in code. |
| B101 (assert_used) | n/a | — | — | Rule disabled in `bandit.yaml`. Asserts exist only in the test suite, which is excluded from the scan; the application uses explicit error responses. |

Result after triage: **0 findings at any severity** (`reports/bandit.txt`).

Suppressions are per line and carry a justification. A blanket `--skip B105` across the
project would also hide a genuinely hardcoded secret introduced later.

## 2. Dynamic abuse-case tests

Static analysis cannot see broken authorisation, so five executable abuse cases cover
the OWASP API Security Top 10 items that matter for a payment endpoint:

| Test | OWASP item | What it proves |
|---|---|---|
| TC17 `test_cannot_pay_with_another_users_wallet` | API1 — Broken Object Level Authorisation | A wallet belonging to `user_2` cannot be charged by `user_1` |
| TC17b `test_cannot_pay_with_another_users_card_token` | API1 | A leaked card token is useless from another account |
| TC18 `test_unauthenticated_request_is_rejected` | API2 — Broken Authentication | No identity, no payment, and no state is created |
| TC19 `test_client_supplied_total_is_revalidated_server_side` | API3 — Client-trusted input | A tampered `total` cannot make the caller pay less than the sum of the splits |
| TC19b `test_float_amounts_are_refused` | Defensive input typing | JSON floats cannot represent money exactly and are refused at the boundary |

Each of these asserts the **side effect**, not only the status code: after a rejected
request the audit endpoint must report zero captures. A `403` that still moved money
would pass a status-only assertion.

## 3. What is deliberately not covered

| Area | Why not here | How it is handled instead |
|---|---|---|
| Dependency vulnerabilities | Out of scope for a prototype with 7 pinned dependencies | `pip-audit` / Dependabot in a real pipeline |
| TLS, secret storage, key rotation | Infrastructure concern, no infrastructure in this prototype | Platform responsibility, reviewed at design time |
| Rate limiting / brute force | No authentication service in scope | Gateway-level control |
| PCI-DSS scope and card data storage | The prototype never stores card data — it holds opaque tokens only | Would require a formal audit, not a test suite |
| Accessibility (WCAG 2.2) | The prototype is API-only; there is no user interface to audit | Would need axe-core or Lighthouse against a real UI |

Stating these gaps explicitly is part of the deliverable: a security report that lists
only what was checked, without what was not, overstates the assurance it provides.
