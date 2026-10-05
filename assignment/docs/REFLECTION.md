# Reflection — What Automation Missed, and Where Human Judgement Was Still Necessary

Automating 34 checks for the split payment feature took far less effort than deciding
*what* to automate and *what the result meant*. The suite is green and the defect
injection shows it has real detection power, yet almost every decision that gave the
suite its value came from human reasoning, not from a tool.

The clearest example appeared when the concurrency test failed. Eight parallel requests
with the same idempotency key produced one `201` and seven `200` replays, while my test
demanded `409` responses. The application was correct and the test was wrong. No tool
could have told me that, because both outcomes are legitimate: rejecting a duplicate
while the first request is in flight and replaying the stored response afterwards are
equally safe. What mattered was the invariant underneath — exactly two captures against
the order. Rewriting the assertion around that invariant instead of around status codes
was a judgement about *what a double charge actually is*. Automation executes an
oracle; it does not supply one.

A second limitation was that a passing suite proves almost nothing on its own. All 34
tests passed on the first complete run, which was reassuring and uninformative. I had
to inject three defects deliberately — disabling the idempotency lookup, removing the
sum check, and switching off compensation — to see whether the tests would notice.
They did, and the three failure sets were precisely the ones targeting those risks.
Choosing *those three* defects was again human work: they were selected because they
map to the irreversible financial risks, not because a tool proposed them.

The performance check exposed how easily a number can be mistaken for assurance. My
pytest smoke test reports a p95 around 0.8 ms, which looks excellent and means very
little: it runs in-process against mocked providers, so it measures my own code and
nothing else. Real split payments make several external calls whose latency dominates
the response. The automated check is therefore useful only as a regression detector,
and I set the threshold at 15 ms — roughly fifteen times the observed value — after
weighing sensitivity against flakiness. A tighter budget would catch smaller
regressions but fail randomly on slower CI machines, and a gate that fires randomly
gets ignored. That trade-off is a judgement call with no correct answer.

Static analysis behaved similarly. Bandit produced four "hardcoded password" findings,
all of them string comparisons inside the mock provider. Suppressing the rule globally
would have been quicker, but it would also hide a genuine secret committed later, so I
suppressed the four lines individually with written justifications and set the CI gate
at medium severity. Reading a finding, deciding it is a false positive, and choosing a
suppression that does not create a blind spot is triage, not automation.

Some risks resisted automation entirely. I could not test whether the extra cent in
100.00 ÷ 3 should go to the first split, the largest split, or the customer's own
card — that is a product and accounting decision, and my test merely encodes the
assumption I made. Equally, the suite says nothing about whether the error message
after a declined split is understandable, whether rare multi-currency combinations
behave sensibly, or whether the API would pass an accessibility review, because there
is no interface to review. Those risks are accepted consciously and pushed to
monitoring, behind a feature flag and a canary rollout, with reconciliation alerts as
the detector.

The most important judgement was the release decision itself. Classifying double
charges, incorrect totals and partial charges as blocking while treating latency and
rare combinations as monitorable rests on reversibility: money taken from a customer
cannot be un-taken by a dashboard. No coverage metric encodes that. Automation gave me
fast, repeatable evidence; deciding which evidence was sufficient to ship remained a
human responsibility.
