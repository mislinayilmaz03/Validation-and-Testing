"""TC14-TC16: partial charge and compensation (R3).

Technique: fault injection through the mock provider. A split payment is a
distributed transaction, so the only acceptable outcomes are "all captured"
or "nothing left captured".
"""
import pytest

from conftest import captures, card, post_split, split_body, wallet


@pytest.mark.tc("TC14")
def test_declined_second_split_reverses_the_first(client, order_id):
    """P1: card declined on split 2 -> split 1 is voided, order FAILED."""
    body = split_body(order_id, splits=[
        card("60.00"), card("40.00", "tok_declined"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 402
    payload = resp.json()
    assert payload["status"] == "FAILED"
    assert payload["code"] == "CARD_DECLINED"
    assert payload["compensation"] == "COMPLETED"

    evidence = captures(client, order_id)
    assert evidence["count"] == 0, "money stayed captured after a failed payment"
    assert evidence["total"] == "0.00"


@pytest.mark.tc("TC15")
def test_timeout_on_second_split_triggers_compensation(client, order_id):
    """P2: a provider timeout must not leave a half-paid order."""
    body = split_body(order_id, splits=[
        wallet("40.00"), card("60.00", "tok_timeout"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 402
    assert resp.json()["code"] == "TIMEOUT"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC15b")
def test_wallet_balance_is_restored_after_compensation(client, order_id):
    """The compensation must give the money back, not only change a status."""
    from app import main

    before = main.provider.wallets["w_main"]["balance"]
    body = split_body(order_id, splits=[
        wallet("40.00"), card("60.00", "tok_provider_error"),
    ])

    post_split(client, body)

    assert main.provider.wallets["w_main"]["balance"] == before


@pytest.mark.tc("TC16")
def test_failed_compensation_raises_an_alert_and_is_queued(client, order_id):
    """P3: if the void itself fails, the case must never disappear silently."""
    body = split_body(order_id, splits=[
        card("60.00", "tok_void_fails"), card("40.00", "tok_declined"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 402
    assert resp.json()["compensation"] == "MANUAL_INTERVENTION_REQUIRED"

    ops = client.get("/v1/ops/manual-queue").json()
    assert ops["count"] == 1
    assert "COMPENSATION_FAILED" in ops["alerts"][0]


@pytest.mark.tc("TC16b")
def test_insufficient_wallet_balance_reverses_earlier_splits(client, order_id):
    """P4: the failure is discovered on the last split; atomicity still holds."""
    body = split_body(order_id, splits=[
        card("60.00"), wallet("40.00", "w_low"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 402
    assert resp.json()["code"] == "INSUFFICIENT_FUNDS"
    assert captures(client, order_id)["count"] == 0
