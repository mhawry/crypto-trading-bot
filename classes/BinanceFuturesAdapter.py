from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from binance.enums import *


class BinanceFuturesAdapter:
    """Binance Futures API adapter"""

    def __init__(self, api_key: str, api_secret: str, symbol: str, leverage: int, test=False) -> None:
        self.client = Client(api_key, api_secret, testnet=test)
        self.symbol = symbol
        self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def set_one_way_position_mode(self) -> None:
        """Sets one-way position mode"""
        current_position_mode = self.client.futures_get_position_mode()

        if current_position_mode['dualSidePosition']:
            self.client.futures_change_position_mode(dualSidePosition=False)

    def get_ticker_data(self) -> dict:
        return self.client.futures_orderbook_ticker(symbol=self.symbol)

    def get_position_amount(self) -> float:
        return float(self.client.futures_position_information(symbol=self.symbol)[0]['positionAmt'])

    def get_open_orders(self) -> dict:
        return self.client.futures_get_open_orders(symbol=self.symbol)

    def get_order(self, order_id: int) -> dict:
        return self.client.futures_get_order(symbol=self.symbol, orderId=order_id)

    def create_limit_order(self, side: str, quantity: float, limit_price: float) -> dict:
        try:
            return self.client.futures_create_order(
                symbol=self.symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_LIMIT,
                timeInForce=TIME_IN_FORCE_IOC,
                quantity=quantity,
                price=limit_price
            )
        except BinanceAPIException as e:
            raise Exception(f"Binance API error: {e.message} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def create_stop_order(self, side: str, quantity: float, stop_price: float) -> dict:
        try:
            return self.client.futures_create_order(
                symbol=self.symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                quantity=quantity,
                stopPrice=stop_price
            )
        except BinanceAPIException as e:
            raise Exception(f"Binance API error: {e.message} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def create_take_profit_order(self, side: str, quantity: float, stop_price: float) -> dict:
        try:
            return self.client.futures_create_order(
                symbol=self.symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                quantity=quantity,
                stopPrice=stop_price
            )
        except BinanceAPIException as e:
            raise Exception(f"Binance API error: {e.message} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def buy_limit(self, quantity: float, limit_price: float):
        return self.create_limit_order(SIDE_BUY, quantity, limit_price)

    def set_stop_loss(self, quantity: float, stop_price: float) -> dict:
        return self.create_stop_order(SIDE_SELL, quantity, stop_price)

    def set_take_profit(self, quantity: float, stop_price: float) -> dict:
        return self.create_take_profit_order(SIDE_SELL, quantity, stop_price)
