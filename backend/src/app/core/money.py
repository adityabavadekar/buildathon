"""Money handling and financial arithmetic.

Never use float for money. All amounts are stored and calculated as integer minor
units (paise) or Decimal values with explicit currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.constants import (
    DEFAULT_CURRENCY,
    GATEWAY_RETRY_COST_PAISE,
    OUTREACH_WHATSAPP_COST_PAISE,
)


@dataclass(frozen=True)
class Money:
    """Immutable representation of a monetary value in minor units (paise)."""

    amount_paise: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount_paise, int):
            msg = f"amount_paise must be an integer, got {type(self.amount_paise).__name__}"
            raise TypeError(msg)
        if not self.currency or not isinstance(self.currency, str):
            msg = "currency must be a non-empty string code (e.g. 'INR')"
            raise ValueError(msg)

    def to_decimal(self) -> Decimal:
        """Convert minor units (paise) to major units (rupees) as a Decimal."""
        return (Decimal(self.amount_paise) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @classmethod
    def from_decimal(
        cls, amount_major: Decimal, currency: str = DEFAULT_CURRENCY
    ) -> Money:
        """Construct Money from major units (rupees) Decimal."""
        paise = int(
            (amount_major * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        return cls(amount_paise=paise, currency=currency)

    def format(self) -> str:
        """Format as a human-readable string with explicit currency (e.g. 'INR 1,250.00')."""
        dec = self.to_decimal()
        return f"{self.currency} {dec:,.2f}"

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = (
                f"Cannot add different currencies: {self.currency} and {other.currency}"
            )
            raise ValueError(msg)
        return Money(
            amount_paise=self.amount_paise + other.amount_paise,
            currency=self.currency,
        )

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = f"Cannot subtract different currencies: {self.currency} and {other.currency}"
            raise ValueError(msg)
        return Money(
            amount_paise=self.amount_paise - other.amount_paise,
            currency=self.currency,
        )

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, int):
            return Money(
                amount_paise=self.amount_paise * factor, currency=self.currency
            )
        if isinstance(factor, Decimal):
            new_paise = int(
                (Decimal(self.amount_paise) * factor).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            )
            return Money(amount_paise=new_paise, currency=self.currency)
        return NotImplemented

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = f"Cannot compare {self.currency} with {other.currency}"
            raise ValueError(msg)
        return self.amount_paise < other.amount_paise

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = f"Cannot compare {self.currency} with {other.currency}"
            raise ValueError(msg)
        return self.amount_paise <= other.amount_paise

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = f"Cannot compare {self.currency} with {other.currency}"
            raise ValueError(msg)
        return self.amount_paise > other.amount_paise

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            msg = f"Cannot compare {self.currency} with {other.currency}"
            raise ValueError(msg)
        return self.amount_paise >= other.amount_paise


def calculate_net_recovered_value_paise(
    recovered_amount_paise: int,
    retry_count: int,
    outreach_count: int,
    discount_paise: int = 0,
    *,
    gateway_retry_cost_paise: int = GATEWAY_RETRY_COST_PAISE,
    outreach_cost_paise: int = OUTREACH_WHATSAPP_COST_PAISE,
) -> int:
    """Calculate Net Recovered Value (NRV) in minor units (paise).

    Formula:
      NRV = Recovered_Amount - (Retries * Cost_Gateway + Outreach * Cost_Msg + Discounts)
    """
    total_retry_cost = retry_count * gateway_retry_cost_paise
    total_outreach_cost = outreach_count * outreach_cost_paise
    total_cost = total_retry_cost + total_outreach_cost + discount_paise
    return recovered_amount_paise - total_cost
