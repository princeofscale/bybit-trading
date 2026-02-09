from decimal import Decimal

from data.models import OrderSide, OrderType
from exchange.models import OrderRequest
from exchange.rest_api import _build_order_params


def test_build_order_params_with_sl_tp() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51000"),
    )
    params = _build_order_params(req)
    assert params["stopLossPrice"] == 49000.0
    assert params["takeProfitPrice"] == 51000.0


def test_build_order_params_reduce_only_position_idx() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        reduce_only=True,
        position_idx=2,
    )
    params = _build_order_params(req)
    assert params["reduceOnly"] is True
    assert params["positionIdx"] == 2
