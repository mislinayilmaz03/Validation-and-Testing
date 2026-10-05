"""TC01-TC10: boundary-value analysis and equivalence partitioning on amounts.

Technique: BVA on the split count, the split amount and the order total;
equivalence partitioning for invalid classes (zero, negative, over-precise).
Each invalid case also asserts the atomicity rule: nothing may be captured
when validation fails.
"""
import pytest

from conftest import captures, card, post_split, split_body, wallet


@pytest.mark.tc("TC01")
def test_minimum_split_count_is_accepted(client, order_id):
    """BVA lower valid boundary: exactly 2 instruments."""
    resp = post_split(client, split_body(order_id))

    assert resp.status_code == 201
    assert resp.json()["status"] == "PAID"
    assert captures(client, order_id)["count"] == 2


@pytest.mark.tc("TC02")
def test_single_instrument_is_rejected(client, order_id):
    """BVA invalid below boundary: 1 instrument is not a split payment."""
    body = split_body(order_id, splits=[card("100.00")])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC03")
def test_maximum_split_count_is_accepted(client, order_id):
    """BVA upper valid boundary: exactly 4 instruments."""
    body = split_body(order_id, splits=[
        card("25.00"), card("25.00", "tok_ok_2"),
        wallet("25.00"), wallet("25.00", "w_main"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 201
    assert captures(client, order_id)["count"] == 4
    assert captures(client, order_id)["total"] == "100.00"


@pytest.mark.tc("TC04")
def test_five_splits_are_rejected(client, order_id):
    """BVA invalid above boundary: 5 instruments."""
    body = split_body(order_id, splits=[
        card("20.00"), card("20.00", "tok_ok_2"),
        wallet("20.00"), wallet("20.00"), wallet("20.00"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "TOO_MANY_SPLITS"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC05")
def test_minimum_split_amount_is_accepted(client, order_id):
    """BVA: a split of exactly 1.00 is the lowest valid amount."""
    body = split_body(order_id, splits=[card("99.00"), wallet("1.00")])

    resp = post_split(client, body)

    assert resp.status_code == 201
    assert captures(client, order_id)["total"] == "100.00"


@pytest.mark.tc("TC06")
@pytest.mark.parametrize("amount,other", [("0.99", "99.01"), ("0.00", "100.00")])
def test_split_below_minimum_is_rejected(client, order_id, amount, other):
    """BVA/EP: 0.99 is just below the boundary, 0.00 is the invalid class."""
    body = split_body(order_id, splits=[card(other), wallet(amount)])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC07")
def test_negative_split_cannot_inflate_another_split(client, order_id):
    """EP invalid class: a negative split must not be a way to shift money."""
    body = split_body(order_id, splits=[card("105.00"), wallet("-5.00")])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert captures(client, order_id)["count"] == 0


@pytest.mark.tc("TC08")
def test_total_limit_boundaries(client, order_id):
    """BVA on the order total: 50000.00 is valid, 50000.01 is not."""
    ok = post_split(client, split_body(
        order_id, total="50000.00",
        splits=[card("25000.00"), wallet("25000.00", "w_load")]))
    assert ok.status_code == 201

    over = post_split(client, split_body(
        f"{order_id}_over", total="50000.01",
        splits=[card("25000.00"), wallet("25000.01", "w_load")]))
    assert over.status_code == 400
    assert over.json()["code"] == "AMOUNT_LIMIT_EXCEEDED"


@pytest.mark.tc("TC09")
@pytest.mark.parametrize("a,b", [("60.00", "39.99"), ("60.00", "40.01")])
def test_sum_mismatch_charges_nothing(client, order_id, a, b):
    """Decision rule + atomicity: a mismatching sum captures no money at all."""
    body = split_body(order_id, splits=[card(a), wallet(b)])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "SPLIT_SUM_MISMATCH"
    evidence = captures(client, order_id)
    assert evidence["count"] == 0
    assert evidence["total"] == "0.00"


@pytest.mark.tc("TC10")
def test_indivisible_total_keeps_the_remainder_cent(client, order_id):
    """BVA: 100.00 / 3 must still sum to 100.00 (33.34 + 33.33 + 33.33)."""
    body = split_body(order_id, splits=[
        card("33.34"), card("33.33", "tok_ok_2"), wallet("33.33"),
    ])

    resp = post_split(client, body)

    assert resp.status_code == 201
    assert captures(client, order_id)["total"] == "100.00"


@pytest.mark.tc("TC10b")
def test_over_precise_amount_is_rejected(client, order_id):
    """EP: more than two decimal places is an invalid input class."""
    body = split_body(order_id, splits=[card("66.666666"), wallet("33.333334")])

    resp = post_split(client, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
