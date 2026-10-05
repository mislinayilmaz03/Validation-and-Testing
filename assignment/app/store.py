"""In-memory persistence for the prototype.

A real service would use a database with a unique constraint on
(idempotency_key) and on (order_id, split_index). The structures below model
exactly those constraints so the tests can assert on them.
"""
import hashlib
import json
import threading
from decimal import Decimal


class Conflict(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def body_fingerprint(body: dict) -> str:
    """Stable hash of the request body, used to detect key reuse."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Store:
    def __init__(self):
        self._lock = threading.Lock()
        self.payments: dict[str, dict] = {}
        self.captures: list[dict] = []
        self.idempotency: dict[str, dict] = {}
        self.manual_queue: list[dict] = []
        self.alerts: list[str] = []

    # --- idempotency --------------------------------------------------
    def begin(self, key: str, body: dict) -> dict | None:
        """Reserve an idempotency key.

        Returns the stored response when this is a replay of a completed
        request, or None when the caller should execute the payment.
        Raises Conflict for key reuse with a different body and for a
        concurrent in-flight duplicate.
        """
        fingerprint = body_fingerprint(body)
        with self._lock:
            record = self.idempotency.get(key)
            if record is None:
                self.idempotency[key] = {
                    "fingerprint": fingerprint,
                    "state": "in_flight",
                    "response": None,
                }
                return None
            if record["fingerprint"] != fingerprint:
                raise Conflict(
                    "IDEMPOTENCY_KEY_REUSE",
                    "this idempotency key was already used with a different payload",
                )
            if record["state"] == "in_flight":
                raise Conflict(
                    "IDEMPOTENT_REQUEST_IN_FLIGHT",
                    "an identical request is still being processed",
                )
            return record["response"]

    def complete(self, key: str, response: dict) -> None:
        with self._lock:
            self.idempotency[key]["state"] = "done"
            self.idempotency[key]["response"] = response

    def release(self, key: str) -> None:
        """Free a key after a validation failure so the client can retry."""
        with self._lock:
            record = self.idempotency.get(key)
            if record is not None and record["state"] == "in_flight":
                del self.idempotency[key]

    # --- payments and captures ---------------------------------------
    def save_payment(self, payment: dict) -> None:
        with self._lock:
            self.payments[payment["payment_id"]] = payment

    def add_capture(self, order_id: str, payment_id: str, instrument: str,
                    reference: str, amount: Decimal, capture_id: str) -> None:
        with self._lock:
            self.captures.append({
                "order_id": order_id,
                "payment_id": payment_id,
                "instrument": instrument,
                "reference": reference,
                "amount": amount,
                "capture_id": capture_id,
                "state": "CAPTURED",
            })

    def mark_voided(self, capture_id: str) -> None:
        with self._lock:
            for capture in self.captures:
                if capture["capture_id"] == capture_id:
                    capture["state"] = "VOIDED"

    def active_captures(self, order_id: str) -> list[dict]:
        return [c for c in self.captures
                if c["order_id"] == order_id and c["state"] == "CAPTURED"]

    def captured_total(self, order_id: str) -> Decimal:
        return sum((c["amount"] for c in self.active_captures(order_id)), Decimal("0.00"))

    def enqueue_manual(self, item: dict, alert: str) -> None:
        with self._lock:
            self.manual_queue.append(item)
            self.alerts.append(alert)

    def reset(self) -> None:
        with self._lock:
            self.payments.clear()
            self.captures.clear()
            self.idempotency.clear()
            self.manual_queue.clear()
            self.alerts.clear()
