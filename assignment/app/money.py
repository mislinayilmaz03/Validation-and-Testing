"""Money arithmetic for split payments.

All amounts are handled as Decimal with a 2-place scale. Floating point is
never used, because binary floats cannot represent 0.01 exactly and the error
accumulates across splits (risk R2 - incorrect totals).
"""
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")

MIN_SPLITS = 2
MAX_SPLITS = 4
MIN_SPLIT_AMOUNT = Decimal("1.00")
MAX_TOTAL = Decimal("50000.00")


class AmountError(ValueError):
    """Raised with a stable machine-readable code for the API layer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_amount(raw) -> Decimal:
    """Parse an amount sent as a string into a 2-decimal Decimal."""
    if isinstance(raw, float):
        raise AmountError("VALIDATION_ERROR", "amounts must be sent as strings, not floats")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise AmountError("VALIDATION_ERROR", f"amount '{raw}' is not a valid decimal")
    if value != value.quantize(CENT):
        raise AmountError("VALIDATION_ERROR", f"amount '{raw}' has more than 2 decimal places")
    return value.quantize(CENT)


def distribute(total: Decimal, parts: int) -> list[Decimal]:
    """Split `total` into `parts` shares that sum back to exactly `total`.

    The indivisible remainder cents are assigned deterministically to the
    first shares, so 100.00 / 3 becomes 33.34 + 33.33 + 33.33.
    """
    if parts < 1:
        raise AmountError("VALIDATION_ERROR", "parts must be >= 1")
    total_cents = int((total * 100).to_integral_value())
    base, remainder = divmod(total_cents, parts)
    shares = [base + (1 if i < remainder else 0) for i in range(parts)]
    return [(Decimal(c) / 100).quantize(CENT) for c in shares]


def validate_split_plan(total: Decimal, amounts: list[Decimal]) -> None:
    """Validate the split plan. Raises AmountError with a stable code."""
    if len(amounts) < MIN_SPLITS:
        raise AmountError(
            "VALIDATION_ERROR",
            f"a split payment needs at least {MIN_SPLITS} instruments",
        )
    if len(amounts) > MAX_SPLITS:
        raise AmountError(
            "TOO_MANY_SPLITS",
            f"a split payment allows at most {MAX_SPLITS} instruments",
        )
    if total <= 0:
        raise AmountError("VALIDATION_ERROR", "total must be greater than zero")
    if total > MAX_TOTAL:
        raise AmountError(
            "AMOUNT_LIMIT_EXCEEDED",
            f"total must not exceed {MAX_TOTAL}",
        )
    for amount in amounts:
        if amount < MIN_SPLIT_AMOUNT:
            raise AmountError(
                "VALIDATION_ERROR",
                f"each split must be at least {MIN_SPLIT_AMOUNT}",
            )
    if sum(amounts) != total:
        raise AmountError(
            "SPLIT_SUM_MISMATCH",
            f"splits sum to {sum(amounts)} but the total is {total}",
        )
