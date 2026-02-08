from decimal import Decimal

from pydantic import BaseModel


class PerPairRiskLimit(BaseModel):
    symbol: str
    max_position_size_usd: Decimal = Decimal("10000")
    max_leverage: Decimal = Decimal("3.0")
    max_risk_pct: Decimal = Decimal("0.02")


class PortfolioRiskLimits(BaseModel):
    max_total_exposure_usd: Decimal = Decimal("50000")
    max_correlated_exposure_pct: Decimal = Decimal("0.20")
    max_single_asset_pct: Decimal = Decimal("0.30")
    funding_arb_allocation_pct: Decimal = Decimal("0.30")
