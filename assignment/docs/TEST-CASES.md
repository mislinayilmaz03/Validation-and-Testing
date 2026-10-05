# Test Case Design and Traceability

Feature under test: **split payment** — one order total paid with 2–4 instruments
(cards and wallets) in a single request.

The assignment asks for at least 12 designed test cases. 23 are designed below and
**all 23 are automated**, which expands to 34 executed pytest cases because four of
them are parameterised. Every case states the design technique it comes from and the
risk it covers, so a reviewer can see *why* the case exists rather than only *what*
it does.

Risk IDs refer to the risk analysis in `docs/TECHNICAL-REPORT` (R1 double charge,
R2 incorrect totals, R3 partial charge, R4 timeout/latency, R6 regression,
R7 authorisation, R8 race condition).

| TC | Title | Technique | Risk | Input | Expected result | Automated test |
|----|-------|-----------|------|-------|-----------------|----------------|
| TC01 | Minimum split count accepted | BVA — lower valid boundary | R2 | 2 instruments, 60.00 + 40.00 = 100.00 | `201 PAID`, 2 captures | `test_boundary_values.py::test_minimum_split_count_is_accepted` |
| TC02 | Single instrument rejected | BVA — invalid below boundary | R2 | 1 instrument, 100.00 | `400 VALIDATION_ERROR`, 0 captures | `::test_single_instrument_is_rejected` |
| TC03 | Maximum split count accepted | BVA — upper valid boundary | R2 | 4 × 25.00 | `201 PAID`, 4 captures, total 100.00 | `::test_maximum_split_count_is_accepted` |
| TC04 | Five splits rejected | BVA — invalid above boundary | R2 | 5 × 20.00 | `400 TOO_MANY_SPLITS`, 0 captures | `::test_five_splits_are_rejected` |
| TC05 | Minimum split amount accepted | BVA | R2 | 99.00 + 1.00 | `201 PAID`, total 100.00 | `::test_minimum_split_amount_is_accepted` |
| TC06 | Split below minimum rejected | BVA + equivalence partitioning | R2 | 0.99 and 0.00 (2 variants) | `400 VALIDATION_ERROR`, 0 captures | `::test_split_below_minimum_is_rejected` |
| TC07 | Negative split rejected | EP — invalid class | R2, R7 | 105.00 + (−5.00) | `400 VALIDATION_ERROR`, 0 captures | `::test_negative_split_cannot_inflate_another_split` |
| TC08 | Order total limit boundaries | BVA — both sides of the limit | R2 | 50 000.00 and 50 000.01 | `201` then `400 AMOUNT_LIMIT_EXCEEDED` | `::test_total_limit_boundaries` |
| TC09 | Sum mismatch charges nothing | Decision rule + atomicity | R2, R3 | 60.00 + 39.99 / 60.00 + 40.01 | `400 SPLIT_SUM_MISMATCH`, 0 captures | `::test_sum_mismatch_charges_nothing` |
| TC10 | Indivisible total keeps the remainder cent | BVA — rounding boundary | R2 | 33.34 + 33.33 + 33.33 | `201`, captured total exactly 100.00 | `::test_indivisible_total_keeps_the_remainder_cent` |
| TC10b | Over-precise amount rejected | EP — invalid class | R2 | 66.666666 | `400 VALIDATION_ERROR` | `::test_over_precise_amount_is_rejected` |
| TC11 | Replay with the same key charges once | State-based (idempotency) | **R1** | same key + same body, twice | `201` then `200`, same `payment_id`, still 2 captures | `test_idempotency.py::test_replay_with_same_key_charges_once` |
| TC12 | Same key, different body is a conflict | State-based, negative | **R1** | same key, different order | `409 IDEMPOTENCY_KEY_REUSE`, 0 captures | `::test_same_key_with_different_body_is_a_conflict` |
| TC13 | Concurrent duplicates do not double charge | Concurrency test | **R1, R8** | 8 parallel identical requests | exactly one `201`; others `200`/`409`; 2 captures | `::test_concurrent_duplicates_do_not_double_charge` |
| TC13b | Missing idempotency key rejected | Negative test | R1 | no `Idempotency-Key` header | `400 IDEMPOTENCY_KEY_REQUIRED` | `::test_missing_idempotency_key_is_rejected` |
| TC14 | Declined second split reverses the first | Fault injection | **R3** | split 2 declined | `402 FAILED`, compensation `COMPLETED`, 0 captures | `test_compensation.py::test_declined_second_split_reverses_the_first` |
| TC15 | Timeout triggers compensation | Fault injection | **R3, R4** | split 2 times out | `402 TIMEOUT`, 0 captures | `::test_timeout_on_second_split_triggers_compensation` |
| TC15b | Wallet balance restored | State verification | R3 | provider error after a wallet capture | wallet balance equals the pre-payment value | `::test_wallet_balance_is_restored_after_compensation` |
| TC16 | Failed compensation alerts and queues | Fault injection — error path of the error path | R3 | void itself fails | `MANUAL_INTERVENTION_REQUIRED`, 1 queue item, alert raised | `::test_failed_compensation_raises_an_alert_and_is_queued` |
| TC16b | Insufficient balance on the last split | Fault injection | R3 | 4th split exceeds the wallet balance | `402 INSUFFICIENT_FUNDS`, 0 captures | `::test_insufficient_wallet_balance_reverses_earlier_splits` |
| TC17 | Another user's wallet cannot be used | Abuse case — OWASP API1 (BOLA) | **R7** | wallet owned by `user_2` | `403 FORBIDDEN_INSTRUMENT`, 0 captures | `test_security.py::test_cannot_pay_with_another_users_wallet` |
| TC17b | Another user's card token cannot be used | Abuse case — API1 | R7 | leaked card token | `403 FORBIDDEN_INSTRUMENT` | `::test_cannot_pay_with_another_users_card_token` |
| TC18 | Unauthenticated request rejected | Negative security test | R7 | no identity header | `401 UNAUTHENTICATED`, no state created | `::test_unauthenticated_request_is_rejected` |
| TC19 | Client-supplied total re-validated | Abuse case — client-trusted input | R2, R7 | total 10.00, splits sum 100.00 | `400 SPLIT_SUM_MISMATCH` | `::test_client_supplied_total_is_revalidated_server_side` |
| TC19b | JSON float amounts refused | Defensive input typing | R2 | `60.0` as a JSON number | `400 VALIDATION_ERROR` | `::test_float_amounts_are_refused` |
| TC20 | Payment reaches PAID and is queryable | State-transition testing | R6 | happy path then `GET /v1/payments/{id}` | stored state `PAID`, total and splits match | `test_state_and_flag.py::test_payment_reaches_paid_state_and_is_queryable` |
| TC20b | Payment reaches FAILED | State-transition testing | R6 | declined split | stored state `FAILED` with cause | `::test_payment_reaches_failed_state` |
| TC21 | Feature flag off disables the endpoint | Configuration test — rollback control | R6 | `SPLIT_PAYMENT_ENABLED=false` | `404 FEATURE_DISABLED`, `/healthz` reports it | `::test_feature_flag_off_disables_the_endpoint` |
| TC21b | Unknown payment returns 404 | Negative path | — | unknown id | `404 NOT_FOUND` | `::test_unknown_payment_returns_not_found` |
| TC22 | Distribution preserves the total | **Property-based** (Hypothesis, 300 examples) | R2 | random totals × 2–4 parts | `sum(shares) == total`, max 2 decimals, balanced | `test_properties.py::test_distribution_preserves_the_total` |
| TC22b | Every share stays above the minimum | Property-based (200 examples) | R2 | random totals × 2–4 parts | `min(shares) >= 1.00` | `::test_every_share_stays_above_the_minimum` |
| TC23 | Latency budget (performance check) | Performance smoke with a threshold | **R4** | 200 sequential split payments | p95 < 15 ms, mean < 10 ms | `test_performance_smoke.py::test_split_payment_latency_budget` |

## Coverage by technique

| Technique | Cases |
|---|---|
| Boundary-value analysis | TC01–TC06, TC08, TC10 |
| Equivalence partitioning | TC02, TC06, TC07, TC10b, TC19b |
| Decision rules / atomicity | TC09, TC14–TC16b |
| State-transition testing | TC11–TC13b, TC20, TC20b |
| Concurrency testing | TC13 |
| Fault injection | TC14–TC16b |
| Abuse-case (security) testing | TC17–TC19b |
| Property-based testing | TC22, TC22b |
| Performance testing | TC23 |
| Configuration / rollback testing | TC21 |

## Coverage by risk

| Risk | Covered by | Blocking? |
|---|---|---|
| R1 double charge | TC11, TC12, TC13, TC13b | Yes |
| R2 incorrect totals | TC01–TC10b, TC19, TC19b, TC22, TC22b | Yes |
| R3 partial charge | TC09, TC14, TC15, TC15b, TC16, TC16b | Yes |
| R4 timeout / latency | TC15, TC23 (+ `perf/k6-split-smoke.js`) | Threshold only |
| R6 regression | TC20, TC20b, TC21, whole suite in CI | Yes |
| R7 authorisation | TC07, TC17, TC17b, TC18, TC19 | Yes |
| R8 race condition | TC13 | Yes |
| R9 rare combinations, R10 accessibility | **not covered** — monitored after deployment | No |

The last row is deliberate, not an omission: see the reflection for why those two
risks are accepted with monitoring instead of tests.

## Defect-injection evidence

A green suite only proves the tests passed. `tools/defect_injection.py` injects three
known defects one at a time and re-runs the suite:

| Mutant | Injected defect | Result |
|---|---|---|
| M1 | Idempotency lookup always misses (replays are charged again) | **Caught** — 3 tests fail (TC11, TC12, TC13) |
| M2 | Sum check removed (splits need not match the total) | **Caught** — 3 tests fail (TC09 ×2, TC19) |
| M3 | Compensation disabled (captured splits stay captured) | **Caught** — 5 tests fail (TC14–TC16b) |

Detection rate: **100 %** — recorded in `reports/defect-injection.json`.
