"""TC11-TC13: idempotency - the control that prevents a double charge (R1).

Technique: state-based testing of the idempotency key plus a concurrency
test. The assertion that matters is not the HTTP status but the number of
captures recorded against the order.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import ENDPOINT, USER, captures, post_split, split_body


@pytest.mark.tc("TC11")
def test_replay_with_same_key_charges_once(client, order_id):
    """I1: the same key and body twice -> one payment, one set of captures."""
    key = str(uuid.uuid4())
    body = split_body(order_id)

    first = post_split(client, body, key=key)
    second = post_split(client, body, key=key)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["payment_id"] == second.json()["payment_id"]

    evidence = captures(client, order_id)
    assert evidence["count"] == 2, "replay created extra captures - double charge"
    assert evidence["total"] == "100.00"


@pytest.mark.tc("TC12")
def test_same_key_with_different_body_is_a_conflict(client, order_id):
    """I2: key reuse with a different payload must never be silently accepted."""
    key = str(uuid.uuid4())
    post_split(client, split_body(order_id), key=key)

    resp = post_split(client, split_body(f"{order_id}_b"), key=key)

    assert resp.status_code == 409
    assert resp.json()["code"] == "IDEMPOTENCY_KEY_REUSE"
    assert captures(client, f"{order_id}_b")["count"] == 0


@pytest.mark.tc("TC13")
def test_concurrent_duplicates_do_not_double_charge(client, order_id):
    """I3: 8 parallel identical requests must still produce one payment.

    Two outcomes are legitimate for the losers of the race: 409 while the
    first request is still in flight, or 200 replaying the stored response
    once it has completed. The invariant that must hold either way is the
    number of captures - that is what a double charge would break.
    """
    key = str(uuid.uuid4())
    body = split_body(order_id)
    headers = {"X-User-Id": USER, "Idempotency-Key": key}

    def send(_):
        return client.post(ENDPOINT, json=body, headers=headers)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(send, range(8)))

    created = [r for r in responses if r.status_code == 201]
    losers = [r for r in responses if r.status_code != 201]

    assert len(created) == 1, "more than one request created a payment"
    assert all(r.status_code in (200, 409) for r in losers), \
        f"unexpected statuses: {[r.status_code for r in losers]}"

    payment_id = created[0].json()["payment_id"]
    for loser in (r for r in losers if r.status_code == 200):
        assert loser.json()["payment_id"] == payment_id, "replay returned a new payment"
    for loser in (r for r in losers if r.status_code == 409):
        assert loser.json()["code"] == "IDEMPOTENT_REQUEST_IN_FLIGHT"

    evidence = captures(client, order_id)
    assert evidence["count"] == 2, "concurrent duplicates created extra captures"
    assert evidence["total"] == "100.00"


@pytest.mark.tc("TC13b")
def test_missing_idempotency_key_is_rejected(client, order_id):
    """A payment request without a key cannot be made safely retryable."""
    resp = client.post(ENDPOINT, json=split_body(order_id),
                       headers={"X-User-Id": USER})

    assert resp.status_code == 400
    assert resp.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
