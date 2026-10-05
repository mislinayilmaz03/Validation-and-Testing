"""TC22: property-based testing of the cent distribution (R2).

Technique: instead of enumerating examples, the invariants are stated once
and Hypothesis searches for a counter-example. This is the direct answer to
the pesticide paradox: the inputs change on every run.
"""
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import MIN_SPLIT_AMOUNT, distribute


@pytest.mark.tc("TC22")
@settings(max_examples=300, deadline=None)
@given(
    total_cents=st.integers(min_value=200, max_value=5_000_000),
    parts=st.integers(min_value=2, max_value=4),
)
def test_distribution_preserves_the_total(total_cents, parts):
    total = (Decimal(total_cents) / 100).quantize(Decimal("0.01"))
    shares = distribute(total, parts)

    assert len(shares) == parts
    assert sum(shares) == total, "cents were created or lost"
    assert all(s.as_tuple().exponent >= -2 for s in shares), "sub-cent precision"
    assert max(shares) - min(shares) <= Decimal("0.01"), "shares are not balanced"


@pytest.mark.tc("TC22b")
@settings(max_examples=200, deadline=None)
@given(
    total_cents=st.integers(min_value=400, max_value=5_000_000),
    parts=st.integers(min_value=2, max_value=4),
)
def test_every_share_stays_above_the_minimum(total_cents, parts):
    total = (Decimal(total_cents) / 100).quantize(Decimal("0.01"))
    shares = distribute(total, parts)

    assert min(shares) >= MIN_SPLIT_AMOUNT
