import requests


class TelegramAdapter:
    """Telegram API adapter"""

    def __init__(self, token: str) -> None:
        self.token = token

    def send_message(self, chat_id: int, text: str) -> None:
        requests.get(f"https://api.telegram.org/bot{self.token}/sendMessage?chat_id={chat_id}&text={text}")
