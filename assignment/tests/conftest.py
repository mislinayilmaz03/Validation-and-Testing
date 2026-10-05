import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main  # noqa: E402

ENDPOINT = "/v1/payments/split"
USER = "user_1"


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts from an empty store and a fresh mock provider."""
    os.environ["SPLIT_PAYMENT_ENABLED"] = "true"
    main.reset_state()
    yield
    main.reset_state()


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def order_id():
    return f"ord_{uuid.uuid4().hex[:8]}"


def new_key():
    return str(uuid.uuid4())


def split_body(order_id, total="100.00", splits=None):
    """Default happy-path payload: 60.00 on a card + 40.00 from a wallet."""
    if splits is None:
        splits = [
            {"instrument": "card", "token": "tok_ok", "amount": "60.00"},
            {"instrument": "wallet", "wallet_id": "w_main", "amount": "40.00"},
        ]
    return {"order_id": order_id, "currency": "TRY", "total": total, "splits": splits}


def post_split(client, body, key=None, user=USER):
    headers = {"X-User-Id": user}
    if key is not None:
        headers["Idempotency-Key"] = key
    else:
        headers["Idempotency-Key"] = new_key()
    return client.post(ENDPOINT, json=body, headers=headers)


def captures(client, order_id):
    """Audit view used as double-charge evidence."""
    return client.get(f"/v1/orders/{order_id}/captures").json()


def card(amount, token="tok_ok"):
    return {"instrument": "card", "token": token, "amount": amount}


def wallet(amount, wallet_id="w_main"):
    return {"instrument": "wallet", "wallet_id": wallet_id, "amount": amount}
