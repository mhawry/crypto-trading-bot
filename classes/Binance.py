from binance.client import Client


class Binance:
    """Telegram API wrapper"""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.client = Client(api_key, api_secret)

    def get_depth(self, symbol: str) -> dict:
        """Get the depth for a symbol/pair

        :param symbol: Symbol/pair to get depth for
        """

        return self.client.get_order_book(symbol=symbol)

    def get_all_tickers(self) -> dict:
        """this is just for testing"""

        return self.client.get_all_tickers()
