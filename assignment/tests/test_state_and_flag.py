"""TC20-TC21: state transitions and the feature-flag rollback control.

Technique: state-transition testing on the payment lifecycle, plus a
configuration test that proves the rollback path actually works. A rollback
plan that is never exercised is not evidence.
"""
import os

import pytest

from conftest import ENDPOINT, USER, card, post_split, split_body, wallet


@pytest.mark.tc("TC20")
def test_payment_reaches_paid_state_and_is_queryable(client, order_id):
    """PENDING -> PAID: the stored payment must match the response."""
    resp = post_split(client, split_body(order_id))
    payment_id = resp.json()["payment_id"]

    stored = client.get(f"/v1/payments/{payment_id}").json()

    assert stored["status"] == "PAID"
    assert stored["total"] == "100.00"
    assert len(stored["splits"]) == 2


@pytest.mark.tc("TC20b")
def test_payment_reaches_failed_state(client, order_id):
    """PENDING -> FAILED: a declined split must be observable afterwards."""
    body = split_body(order_id, splits=[card("60.00"), card("40.00", "tok_declined")])
    resp = post_split(client, body)
    payment_id = resp.json()["payment_id"]

    stored = client.get(f"/v1/payments/{payment_id}").json()

    assert stored["status"] == "FAILED"
    assert stored["code"] == "CARD_DECLINED"


@pytest.mark.tc("TC21")
def test_feature_flag_off_disables_the_endpoint(client, order_id):
    """Rollback evidence: the feature can be switched off without a deploy."""
    os.environ["SPLIT_PAYMENT_ENABLED"] = "false"
    try:
        resp = client.post(ENDPOINT, json=split_body(order_id),
                           headers={"X-User-Id": USER, "Idempotency-Key": "k-flag"})

        assert resp.status_code == 404
        assert resp.json()["code"] == "FEATURE_DISABLED"
        assert client.get("/healthz").json()["split_payment_enabled"] is False
    finally:
        os.environ["SPLIT_PAYMENT_ENABLED"] = "true"


@pytest.mark.tc("TC21b")
def test_unknown_payment_returns_not_found(client):
    """Negative path on the read model."""
    resp = client.get("/v1/payments/pay_does_not_exist")

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
