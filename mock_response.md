```python
import pytest
from pricing.cart import apply_discount, bulk_price


def test_apply_discount_rounds_to_cents():
    assert apply_discount(19.99, 15) == 16.99


def test_apply_discount_rejects_pct_over_100():
    with pytest.raises(ValueError):
        apply_discount(10, 101)


def test_apply_discount_rejects_negative_price():
    with pytest.raises(ValueError):
        apply_discount(-1, 10)


def test_apply_discount_boundaries():
    assert apply_discount(50, 0) == 50
    assert apply_discount(50, 100) == 0


def test_bulk_price_tier_boundaries():
    assert bulk_price(1, 9) == 9
    assert bulk_price(1, 10) == 9.5
    assert bulk_price(1, 49) == 46.55
    assert bulk_price(1, 50) == 42.5


def test_bulk_price_rejects_zero_qty():
    with pytest.raises(ValueError):
        bulk_price(5, 0)


# --- the next three are deliberately bad, to exercise each failure mode ---

def test_bulk_price_wrong_expectation():
    assert bulk_price(2, 10) == 20          # failure mode 1: fails (real answer is 19.0)


def test_placeholder():
    bulk_price(1, 1)
    assert True                             # failure mode 2: useless


def test_discount_ten_percent():
    assert apply_discount(100, 10) == 90    # failure mode 3: repeats existing test
```
