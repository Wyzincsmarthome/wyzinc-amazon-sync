# src/core/pricing.py
"""
Pricing engine. Calculates the final Amazon selling price from a cost,
using margin tiers, VAT, shipping, Amazon referral fee and DST surcharge
defined in config/rules.json.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.settings import settings


@dataclass(frozen=True)
class PricingResult:
    cost: float
    floor_price: float
    final_price: float
    margin_used: float


class PricingEngine:
    def __init__(self) -> None:
        rules = settings.load_rules()["pricing"]
        self.vat_rate: float = rules["vat_rate"]
        self.shipping_cost: float = rules["shipping_cost"]
        self.dst_surcharge: float = rules["dst_surcharge"]
        self.undercut_step: float = rules["undercut_step"]
        self.margin_tiers: list[dict] = rules["margin_tiers"]
        self.referral_tiers: dict = rules["amazon_referral"]

    def _margin_for_cost(self, cost: float) -> float:
        for tier in self.margin_tiers:
            if tier["min_cost"] <= cost <= tier["max_cost"]:
                return float(tier["margin"])
        return float(self.margin_tiers[-1]["margin"])

    def _referral_rate(self, gross_price: float) -> float:
        tier_1 = self.referral_tiers["tier_1"]
        if gross_price <= tier_1["threshold"]:
            return float(tier_1["rate"])
        return float(self.referral_tiers["tier_2"]["rate"])

    def calculate_price(
        self,
        cost: float,
        competitor_price: Optional[float] = None,
    ) -> PricingResult:
        if cost <= 0:
            raise ValueError("cost must be positive")

        margin = self._margin_for_cost(cost)
        base = cost + self.shipping_cost
        # gross = base * (1 + vat) * (1 + dst) / (1 - referral - margin)
        # Solve iteratively because referral depends on gross.
        gross = base * (1 + self.vat_rate) * (1 + self.dst_surcharge)
        for _ in range(8):
            referral = self._referral_rate(gross)
            denom = 1 - referral - margin
            if denom <= 0:
                raise ValueError("margin + referral >= 1, cannot price")
            new_gross = base * (1 + self.vat_rate) * (1 + self.dst_surcharge) / denom
            if abs(new_gross - gross) < 0.005:
                gross = new_gross
                break
            gross = new_gross

        floor_price = round(gross, 2)
        final_price = floor_price
        if competitor_price is not None and competitor_price - self.undercut_step >= floor_price:
            final_price = round(competitor_price - self.undercut_step, 2)

        return PricingResult(
            cost=cost,
            floor_price=floor_price,
            final_price=final_price,
            margin_used=margin,
        )


pricing_engine = PricingEngine()
