import math
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from binance.enums import *


class BinanceFuturesAdapter:
    """Binance Futures API adapter"""

    def __init__(self, api_key: str, api_secret: str, symbol: str, leverage: int, test=False) -> None:
        self.client = Client(api_key, api_secret, testnet=test)
        self.symbol = symbol
        self.leverage_data = self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        self.set_one_way_position_mode()

    def set_one_way_position_mode(self) -> None:
        """Sets the position mode to one-way"""
        current_position_mode = self.client.futures_get_position_mode()

        if current_position_mode['dualSidePosition']:
            self.client.futures_change_position_mode(dualSidePosition=False)

    def get_available_balance(self) -> float:
        """Returns the available balance in the futures account

        :rtype float
        """
        return float(self.client.futures_account()['availableBalance'])

    def get_usdt_trade_size(self, allocation: float) -> float:
        """This will return the size of the trade we should use in USDT.

        :param allocation: Percentage of available balance to use for the trade.
        :rtype float
        """
        return min(math.floor(self.get_available_balance())*allocation, float(self.leverage_data['maxNotionalValue'])*allocation)

    def get_mark_price(self) -> float:
        return float(self.client.futures_mark_price(symbol=self.symbol)['markPrice'])

    def create_order(self, side: str, quantity: float, limit_price: float) -> dict:
        """This will create the Binance order.

        TODO update param descriptions below

        :param side: Long or short
        :param quantity:
        :param limit_price:
        :rtype: dict
        :raises BinanceAPIException: If there are issues with the API
        :raises BinanceOrderException: If the order can't be created for some reason
        """

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
            raise Exception(f"Binance API error: {e.response} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def buy(self, quantity: float, limit_price: float):
        """Buy crypto"""
        return self.create_order(SIDE_BUY, quantity, limit_price)

    def sell(self, quantity: float, limit_price: float):
        """Sell crypto"""
        return self.create_order(SIDE_SELL, quantity, limit_price)