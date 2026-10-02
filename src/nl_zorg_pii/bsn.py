"""Burgerservicenummer (BSN) validation using the 11-proef (elfproef)."""

from __future__ import annotations

_WEIGHTS = (9, 8, 7, 6, 5, 4, 3, 2, -1)


def is_valid_bsn(value: str) -> bool:
    """Return True if ``value`` is a syntactically valid BSN.

    Rules: 8 or 9 digits (8-digit numbers get a leading zero), and the weighted
    sum ``9*d1 + 8*d2 + ... + 2*d8 - d9`` must be divisible by 11. Numbers such
    as 000000000 are rejected.
    """
    digits = value.strip().replace(" ", "").replace(".", "").replace("-", "")
    if not digits.isdigit() or len(digits) not in (8, 9):
        return False
    digits = digits.zfill(9)
    if digits == "000000000":
        return False
    total = sum(int(d) * w for d, w in zip(digits, _WEIGHTS, strict=True))
    return total % 11 == 0


def example_bsn(seed: int = 0) -> str:
    """Return a syntactically valid BSN for use in tests and examples.

    The number is derived from ``seed`` so tests can create several distinct
    values. It is not tied to any real person; validity is purely arithmetic.
    """
    base = 100_000_000 + (abs(seed) % 8_999_999) * 100
    for candidate in range(base, base + 100):
        value = str(candidate)
        if is_valid_bsn(value):
            return value
    raise RuntimeError("no valid BSN found for seed")  # pragma: no cover
