import uuid

import structlog

from data.models import OrderSide, OrderStatus, OrderType
from exchange.errors import ExchangeError
from exchange.models import InFlightOrder, InFlightOrderStatus, OrderRequest, OrderResult
from exchange.rest_api import RestApi

logger = structlog.get_logger("order_manager")


class OrderManager:
    def __init__(self, rest_api: RestApi) -> None:
        self._rest_api = rest_api
        self._in_flight: dict[str, InFlightOrder] = {}

    async def submit_order(self, request: OrderRequest, strategy_name: str = "") -> InFlightOrder:
        client_id = request.client_order_id or str(uuid.uuid4())
        request.client_order_id = client_id

        in_flight = InFlightOrder(
            client_order_id=client_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            strategy_name=strategy_name,
        )
        self._in_flight[client_id] = in_flight

        try:
            result = await self._rest_api.place_order(request)
            in_flight.exchange_order_id = result.order_id
            in_flight.status = InFlightOrderStatus.OPEN
            await logger.ainfo(
                "order_submitted",
                client_id=client_id,
                exchange_id=result.order_id,
                symbol=request.symbol,
                side=request.side,
                type=request.order_type,
                qty=str(request.quantity),
                price=str(request.price) if request.price else "market",
            )
            return in_flight
        except ExchangeError as e:
            in_flight.status = InFlightOrderStatus.DONE
            await logger.aerror(
                "order_submit_failed",
                client_id=client_id,
                error=str(e),
                error_type=e.error_type,
            )
            raise

    async def cancel_order(self, client_order_id: str) -> None:
        in_flight = self._in_flight.get(client_order_id)
        if not in_flight:
            await logger.awarning("cancel_unknown_order", client_id=client_order_id)
            return

        if in_flight.status == InFlightOrderStatus.DONE:
            return

        in_flight.status = InFlightOrderStatus.PENDING_CANCEL
        try:
            await self._rest_api.cancel_order(in_flight.exchange_order_id, in_flight.symbol)
            in_flight.status = InFlightOrderStatus.DONE
            await logger.ainfo("order_cancelled", client_id=client_order_id)
        except ExchangeError as e:
            if e.error_type.value == "order_not_found":
                in_flight.status = InFlightOrderStatus.DONE
            else:
                in_flight.status = InFlightOrderStatus.OPEN
                raise

    async def cancel_all(self, symbol: str) -> None:
        await self._rest_api.cancel_all_orders(symbol)
        for order in self._in_flight.values():
            if order.symbol == symbol and order.status != InFlightOrderStatus.DONE:
                order.status = InFlightOrderStatus.DONE
        await logger.ainfo("all_orders_cancelled", symbol=symbol)

    def update_from_exchange(self, order_result: OrderResult) -> None:
        for order in self._in_flight.values():
            if order.exchange_order_id == order_result.order_id:
                order.filled_qty = order_result.filled_qty
                if order_result.status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
                    order.status = InFlightOrderStatus.DONE
                elif order_result.status == OrderStatus.PARTIALLY_FILLED:
                    order.status = InFlightOrderStatus.PARTIALLY_FILLED
                return

    def get_open_orders(self, symbol: str | None = None) -> list[InFlightOrder]:
        orders = [
            o for o in self._in_flight.values()
            if o.status not in {InFlightOrderStatus.DONE}
        ]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_order(self, client_order_id: str) -> InFlightOrder | None:
        return self._in_flight.get(client_order_id)

    def cleanup_done_orders(self, keep_last: int = 100) -> int:
        done = [
            cid for cid, o in self._in_flight.items()
            if o.status == InFlightOrderStatus.DONE
        ]
        to_remove = done[:-keep_last] if len(done) > keep_last else []
        for cid in to_remove:
            del self._in_flight[cid]
        return len(to_remove)

    @property
    def in_flight_count(self) -> int:
        return len([o for o in self._in_flight.values() if o.status != InFlightOrderStatus.DONE])
