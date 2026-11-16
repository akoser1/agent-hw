#!/usr/bin/env bash
# Builds ./demo_repo: a tiny git repo with one committed version and one uncommitted change.
set -euo pipefail
rm -rf demo_repo && mkdir -p demo_repo/pricing demo_repo/tests && cd demo_repo
git init -q && git config user.email demo@example.com && git config user.name demo
touch pricing/__init__.py
cat > pricing/cart.py <<'PY'
def apply_discount(price, pct):
    return price * (1 - pct / 100)
PY
cat > tests/test_cart.py <<'PY'
from pricing.cart import apply_discount


def test_apply_discount_basic():
    assert apply_discount(100, 10) == 90
PY
git add -A && git commit -qm "v1: apply_discount"
# ---- the uncommitted change DiffTest should test ----
cat > pricing/cart.py <<'PY'
def apply_discount(price, pct):
    """Apply a percentage discount. pct must be in [0, 100]. Result is rounded to cents."""
    if price < 0:
        raise ValueError("price must be non-negative")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    return round(price * (1 - pct / 100), 2)


def bulk_price(unit_price, qty):
    """Tiered bulk pricing: 10+ items get 5% off, 50+ items get 15% off."""
    if qty <= 0:
        raise ValueError("qty must be positive")
    if qty >= 50:
        pct = 15
    elif qty >= 10:
        pct = 5
    else:
        pct = 0
    return apply_discount(unit_price * qty, pct)
PY
echo "demo_repo ready: pricing/cart.py has uncommitted changes vs HEAD"
