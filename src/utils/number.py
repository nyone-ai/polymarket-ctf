"""Numeric helpers: fixed-point price/size normalization."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def to_wei(amount: float, decimals: int) -> int:
    return int(round(amount * (10 ** decimals)))


def from_wei(amount: int, decimals: int) -> float:
    return float(amount) / (10 ** decimals)


def price_to_fixed(price: float) -> int:
    """CLOB prices are scaled by 1e2 (two decimals)."""
    return to_wei(price,  2)


def fixed_to_price(raw: int) -> float:
    return from_wei(raw,  2)


def size_to_fixed(size: float) -> int:
    """CLOB sizes are scaled by 1e2."""
    return to_wei(size,  2)


def round_price(price: float) -> float:
    return float(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def round_size(size: float) -> float:
    return float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fdiv(numerator: float, denominator: float) -> float:
    if denominator <=  0:
        return 0.0
    return numerator / denominator