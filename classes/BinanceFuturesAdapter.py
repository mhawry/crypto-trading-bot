from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from binance.enums import *


class BinanceFuturesAdapter:
    """Binance Futures API adapter"""

    def __init__(self, api_key: str, api_secret: str, test=False) -> None:
        self.client = Client(api_key, api_secret, testnet=test)
        self.set_one_way_position_mode()

    def set_one_way_position_mode(self) -> None:
        """Sets position mode to one-way"""
        current_position_mode = self.client.futures_get_position_mode()

        if current_position_mode['dualSidePosition']:
            self.client.futures_change_position_mode(dualSidePosition=False)

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Sets the leverage to use for a given symbol"""
        return self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def get_tick_size(self, symbol: str) -> float:
        """Gets the tick size for a given symbol"""
        info = self.client.futures_exchange_info()

        for symbol_info in info['symbols']:
            if symbol_info['symbol'] == symbol:
                for symbol_filter in symbol_info['filters']:
                    if symbol_filter['filterType'] == 'PRICE_FILTER':
                        return float(symbol_filter['tickSize'])

    def get_position_information(self, symbol: str) -> dict:
        """Returns position information on a given symbol"""
        return self.client.futures_position_information(symbol=symbol)[0]

    def get_bid_price(self, symbol: str) -> float:
        """Gets the current bid price for a given symbol

        Note: this isn't used right now but could be useful in the future
        """
        return float(self.client.futures_orderbook_ticker(symbol=symbol)['bidPrice'])

    def get_ask_price(self, symbol: str) -> float:
        """Gets the current ask price for a given symbol"""
        return float(self.client.futures_orderbook_ticker(symbol=symbol)['askPrice'])

    def get_open_orders(self, symbol: str) -> dict:
        """Returns current open orders on a given symbol

        TODO this isn't used - we may look into removing it
        """
        return self.client.futures_get_open_orders(symbol=symbol)

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Returns order information on a given symbol and order id

        Note: Binance doesn't allow us to just send the order_id - symbol is required as well
        """
        return self.client.futures_get_order(symbol=symbol, orderId=order_id)

    def _create_limit_order(self, symbol: str, side: str, quantity: float, limit_price: float) -> dict:
        """Generates a new limit order on Binance

        Parameters
        ----------
        symbol : str
            The symbol to open the order on.
        side : str
            The position side (SIDE_BUY or SIDE_SELL)
        quantity : float
            The order amount/size
        limit_price : float
            The limit price to use for the order.

        Returns
        -------
        dict
            A dictionary containing the order data.

        Raises
        ------
        BinanceAPIException
            If the API returns an error
        BinanceOrderException
            If there was an error with the order
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

    def _create_stop_order(self, symbol: str, side: str, quantity: float, stop_price: float) -> dict:
        """Generates a new stop market order on Binance

        Parameters
        ----------
        symbol : str
            The symbol to open the order on.
        side : str
            The position side (SIDE_BUY or SIDE_SELL)
        quantity : float
            The order amount/size
        stop_price : float
            The stop price to use for the order.

        Returns
        -------
        dict
            A dictionary containing the order data.

        Raises
        ------
        BinanceAPIException
            If the API returns an error
        BinanceOrderException
            If there was an error with the order
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

    def _create_trailing_stop_order(self, symbol: str, side: str, quantity: float, activation_price: float, callback_rate: float) -> dict:
        """Generates a new trailing stop market order on Binance

        Parameters
        ----------
        symbol : str
            The symbol to open the order on.
        side : str
            The position side (SIDE_BUY or SIDE_SELL)
        quantity : float
            The order amount/size
        activation_price : float
            The activation price to use for the order.
        callback_rate : float
            The callback rate to use for the order.

        Returns
        -------
        dict
            A dictionary containing the order data.

        Raises
        ------
        BinanceAPIException
            If the API returns an error
        BinanceOrderException
            If there was an error with the order
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
        """Creates a new buy limit order"""
        return self._create_limit_order(symbol, SIDE_BUY, quantity, limit_price)

    def set_stop_loss(self, symbol: str, quantity: float, stop_price: float) -> dict:
        """Creates a new stop-loss order"""
        return self._create_stop_order(symbol, SIDE_SELL, quantity, stop_price)

    def set_trailing_stop(self, symbol: str, quantity: float, activation_price: float, callback_rate: float) -> dict:
        """Creates a new trailing stop order"""
        return self._create_trailing_stop_order(symbol, SIDE_SELL, quantity, activation_price, callback_rate)
