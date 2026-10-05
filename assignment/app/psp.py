"""Mock payment providers with deterministic fault injection.

A real card network cannot be asked to decline or time out on demand, so the
providers are mocked. Behaviour is selected by the instrument identifier,
which keeps the tests deterministic (no flaky external dependency).
"""
from decimal import Decimal


class ProviderDeclined(Exception):
    code = "CARD_DECLINED"


class ProviderTimeout(Exception):
    code = "TIMEOUT"


class ProviderUnavailable(Exception):
    code = "PROVIDER_ERROR"


class InsufficientFunds(Exception):
    code = "INSUFFICIENT_FUNDS"


class CompensationFailed(Exception):
    code = "COMPENSATION_FAILED"


# token -> owner user id. Ownership is what makes the authorisation tests real.
CARD_TOKENS = {
    "tok_ok": "user_1",
    "tok_ok_2": "user_1",
    "tok_declined": "user_1",
    "tok_timeout": "user_1",
    "tok_provider_error": "user_1",
    "tok_void_fails": "user_1",
    "tok_load": "user_1",
    "tok_other_user": "user_2",
}

WALLETS = {
    "w_main": {"owner": "user_1", "balance": Decimal("10000.00")},
    "w_low": {"owner": "user_1", "balance": Decimal("5.00")},
    "w_load": {"owner": "user_1", "balance": Decimal("1000000.00")},
    "w_foreign": {"owner": "user_2", "balance": Decimal("10000.00")},
}


class MockPSP:
    """Captures and voids money, and records every call for assertions."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.wallets = {k: dict(v) for k, v in WALLETS.items()}

    # --- card ---------------------------------------------------------
    def capture_card(self, token: str, amount: Decimal, ref: str) -> str:
        self.calls.append(("capture_card", token, str(amount)))
        # The token comparisons below are fault-injection selectors for the
        # mock provider, not credentials. Bandit B105 is suppressed per line
        # with a justification; see docs/SECURITY-TRIAGE.md.
        if token == "tok_declined":  # nosec B105
            raise ProviderDeclined("card was declined by the issuer")
        if token == "tok_timeout":  # nosec B105
            raise ProviderTimeout("no response from the card network")
        if token == "tok_provider_error":  # nosec B105
            raise ProviderUnavailable("card network returned 500")
        if token not in CARD_TOKENS:
            raise ProviderDeclined("unknown card token")
        return f"cap_card_{ref}"

    def void_card(self, capture_id: str, token: str) -> None:
        self.calls.append(("void_card", token, capture_id))
        # Fault-injection selector, not a credential (see triage document).
        if token == "tok_void_fails":  # nosec B105
            raise CompensationFailed("void rejected by the card network")

    # --- wallet -------------------------------------------------------
    def capture_wallet(self, wallet_id: str, amount: Decimal, ref: str) -> str:
        self.calls.append(("capture_wallet", wallet_id, str(amount)))
        wallet = self.wallets.get(wallet_id)
        if wallet is None:
            raise ProviderDeclined("unknown wallet")
        if wallet["balance"] < amount:
            raise InsufficientFunds("wallet balance is too low")
        wallet["balance"] -= amount
        return f"cap_wallet_{ref}"

    def void_wallet(self, capture_id: str, wallet_id: str, amount: Decimal) -> None:
        self.calls.append(("void_wallet", wallet_id, capture_id))
        self.wallets[wallet_id]["balance"] += amount
