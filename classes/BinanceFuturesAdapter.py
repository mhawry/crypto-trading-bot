from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from binance.enums import *


class BinanceFuturesAdapter:
    """Binance Futures API adapter"""

    def __init__(self, api_key: str, api_secret: str, test=False) -> None:
        self.client = Client(api_key, api_secret, testnet=test)
        self.set_one_way_position_mode()

    def set_one_way_position_mode(self) -> None:
        """Set the position mode to one-way."""
        current_position_mode = self.client.futures_get_position_mode()

        if current_position_mode['dualSidePosition']:
            self.client.futures_change_position_mode(dualSidePosition=False)

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Set the leverage for a given symbol."""
        return self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def get_tick_size(self, symbol: str) -> float:
        """Get the tick size for a given symbol."""
        info = self.client.futures_exchange_info()

        for symbol_info in info['symbols']:
            if symbol_info['symbol'] == symbol:
                for symbol_filter in symbol_info['filters']:
                    if symbol_filter['filterType'] == 'PRICE_FILTER':
                        return float(symbol_filter['tickSize'])

    def get_quantity_precision(self, symbol: str) -> float:
        """Get the quantity precision for a given symbol."""
        info = self.client.futures_exchange_info()

        for symbol_info in info['symbols']:
            if symbol_info['symbol'] == symbol:
                return symbol_info['quantityPrecision']

    def get_margin_balance(self) -> float:
        """Get the margin balance in the account."""
        return float(self.client.futures_account()['totalMarginBalance'])

    def get_position_information(self, symbol: str) -> dict:
        """Get position information on a given symbol"""
        return self.client.futures_position_information(symbol=symbol)[0]

    def get_bid_price(self, symbol: str) -> float:
        """Get the current bid price for a given symbol."""
        return float(self.client.futures_orderbook_ticker(symbol=symbol)['bidPrice'])

    def get_ask_price(self, symbol: str) -> float:
        """Get the current ask price for a given symbol."""
        return float(self.client.futures_orderbook_ticker(symbol=symbol)['askPrice'])

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Get order information for a given symbol and order id.

        Note: Binance doesn't allow us to just send the order_id - symbol is required as well.
        """
        return self.client.futures_get_order(symbol=symbol, orderId=order_id)

    def _send_limit_order(self, symbol: str, side: str, quantity: float, limit_price: float) -> dict:
        """
        Send a new limit order to Binance.

        :param symbol: The symbol to open the order for.
        :param side: The position side (SIDE_BUY or SIDE_SELL).
        :param quantity: The order amount/size.
        :param limit_price: The limit price to use for the order.
        :return: The order data.
        :raise Exception: If the API returns an error or if the order doesn't go through.
        """
        try:
            return self.client.futures_create_order(
                symbol=symbol,
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

    def _send_stop_order(self, symbol: str, side: str, quantity: float, stop_price: float) -> dict:
        """
        Send a new stop market order to Binance.

        :param symbol: The symbol to open the order for.
        :param side: The position side (SIDE_BUY or SIDE_SELL).
        :param quantity: The order amount/size.
        :param stop_price: The stop price to use for the order.
        :return: The order data.
        :raise Exception: If the API returns an error or if the order doesn't go through.
        """
        try:
            return self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                quantity=quantity,
                stopPrice=stop_price
            )
        except BinanceAPIException as e:
            raise Exception(f"Binance API error: {e.message} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def _send_trailing_stop_order(self, symbol: str, side: str, quantity: float, activation_price: float, callback_rate: float) -> dict:
        """
        Send a new trailing stop market order to Binance.

        :param symbol: The symbol to open the order for.
        :param side: The position side (SIDE_BUY or SIDE_SELL).
        :param quantity: The order amount/size.
        :param activation_price: The activation price to use for the order.
        :param callback_rate: The callback rate to use for the order.
        :return: The order data.
        :raise Exception: If the API returns an error or if the order doesn't go through.
        """
        try:
            return self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='TRAILING_STOP_MARKET',
                quantity=quantity,
                activationPrice=activation_price,
                callbackRate=callback_rate
            )
        except BinanceAPIException as e:
            raise Exception(f"Binance API error: {e.message} [{e.status_code}]")
        except BinanceOrderException as e:
            raise Exception(f"Binance order error: {e.message} [{e.code}]")

    def buy_limit(self, symbol: str, quantity: float, limit_price: float):
        """Create a new buy limit order."""
        return self._send_limit_order(symbol, SIDE_BUY, quantity, limit_price)

    def set_stop_loss(self, symbol: str, quantity: float, stop_price: float) -> dict:
        """Create a new stop-loss order."""
        return self._send_stop_order(symbol, SIDE_SELL, quantity, stop_price)

    def set_trailing_stop(self, symbol: str, quantity: float, activation_price: float, callback_rate: float) -> dict:
        """Create a new trailing stop order."""
        return self._send_trailing_stop_order(symbol, SIDE_SELL, quantity, activation_price, callback_rate)
