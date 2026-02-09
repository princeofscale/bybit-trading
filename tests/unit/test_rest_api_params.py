from decimal import Decimal

from data.models import OrderSide, OrderType
from exchange.models import OrderRequest
from exchange.rest_api import _build_order_params, _parse_position


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


def test_parse_position_uses_info_stop_fields_and_ignores_zero() -> None:
    pos = _parse_position(
        {
            "symbol": "XRP/USDT:USDT",
            "side": "long",
            "contracts": "100",
            "entryPrice": "1.45",
            "markPrice": "1.46",
            "unrealizedPnl": "10",
            "info": {
                "positionIdx": "1",
                "stopLoss": "1.42",
                "takeProfit": "1.50",
                "cumRealisedPnl": "0",
            },
        }
    )
    assert pos.stop_loss == Decimal("1.42")
    assert pos.take_profit == Decimal("1.50")

    pos_zero = _parse_position(
        {
            "symbol": "XRP/USDT:USDT",
            "side": "long",
            "contracts": "100",
            "entryPrice": "1.45",
            "markPrice": "1.46",
            "unrealizedPnl": "10",
            "stopLoss": "0",
            "takeProfit": "0",
            "info": {
                "positionIdx": "1",
            },
        }
    )
    assert pos_zero.stop_loss is None
    assert pos_zero.take_profit is None
