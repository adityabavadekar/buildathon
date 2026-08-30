"""Tests for financial calculations, money value object, and NRV computation."""

from decimal import Decimal

import pytest

from app.core.money import Money, calculate_net_recovered_value_paise


def test_money_creation_and_decimal_conversion() -> None:
    m = Money(amount_paise=125050, currency="INR")
    assert m.amount_paise == 125050
    assert m.to_decimal() == Decimal("1250.50")
    assert m.format() == "INR 1,250.50"


def test_money_from_decimal() -> None:
    m = Money.from_decimal(Decimal("499.99"), currency="INR")
    assert m.amount_paise == 49999
    assert m.to_decimal() == Decimal("499.99")


def test_money_arithmetic() -> None:
    m1 = Money(amount_paise=10000, currency="INR")
    m2 = Money(amount_paise=5000, currency="INR")

    added = m1 + m2
    assert added.amount_paise == 15000
    assert added.to_decimal() == Decimal("150.00")

    subtracted = m1 - m2
    assert subtracted.amount_paise == 5000

    multiplied = m1 * 3
    assert multiplied.amount_paise == 30000

    discounted = m1 * Decimal("0.90")
    assert discounted.amount_paise == 9000


def test_money_currency_mismatch_raises() -> None:
    m_inr = Money(amount_paise=1000, currency="INR")
    m_usd = Money(amount_paise=1000, currency="USD")

    with pytest.raises(ValueError, match="Cannot add different currencies"):
        _ = m_inr + m_usd


def test_net_recovered_value_calculation() -> None:
    nrv = calculate_net_recovered_value_paise(
        recovered_amount_paise=500000,
        retry_count=2,
        outreach_count=1,
        discount_paise=25000,
        gateway_retry_cost_paise=250,
        outreach_cost_paise=50,
    )
    assert nrv == 474450
