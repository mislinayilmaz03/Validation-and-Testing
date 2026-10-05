"""TC17-TC19: the security check required by the assignment.

Technique: negative (abuse-case) testing derived from OWASP API Security
Top 10 - API1 broken object level authorisation and API3 excessive data /
client-trusted input.
"""
import pytest

from conftest import ENDPOINT, captures, card, post_split, split_body, wallet


@pytest.mark.tc("TC17")
@pytest.mark.security
def test_cannot_pay_with_another_users_wallet(client, order_id):
    """API1 - BOLA: w_foreign belongs to user_2, the caller is user_1."""
    body = split_body(order_id, splits=[card("60.00"), wallet("40.00", "w_foreign")])

    resp = post_split(client, body, user="user_1")

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN_INSTRUMENT"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC17b")
@pytest.mark.security
def test_cannot_pay_with_another_users_card_token(client, order_id):
    """A leaked card token must not be usable by a different account."""
    body = split_body(order_id, splits=[
        card("60.00", "tok_other_user"), wallet("40.00"),
    ])

    resp = post_split(client, body, user="user_1")

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN_INSTRUMENT"


@pytest.mark.tc("TC18")
@pytest.mark.security
def test_unauthenticated_request_is_rejected(client, order_id):
    """No identity -> no payment, and no state is created."""
    resp = client.post(ENDPOINT, json=split_body(order_id),
                       headers={"Idempotency-Key": "k-1"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHENTICATED"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC19")
@pytest.mark.security
def test_client_supplied_total_is_revalidated_server_side(client, order_id):
    """API3: a tampered total must not let the caller pay less than the sum."""
    body = split_body(order_id, total="10.00",
                      splits=[card("60.00"), wallet("40.00")])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "SPLIT_SUM_MISMATCH"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC19b")
@pytest.mark.security
def test_float_amounts_are_refused(client, order_id):
    """Defensive input typing: JSON floats cannot represent money exactly."""
    body = split_body(order_id, splits=[
        {"instrument": "card", "token": "tok_ok", "amount": 60.0},
        {"instrument": "wallet", "wallet_id": "w_main", "amount": 40.0},
    ])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
