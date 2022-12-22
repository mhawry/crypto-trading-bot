import requests


class TelegramAdapter:
    """Telegram API adapter"""

    def __init__(self, token: str, chat_id: int) -> None:
        self.token = token
        self.chat_id = chat_id

    def send_message(self, text: str) -> None:
        requests.get(f"https://api.telegram.org/bot{self.token}/sendMessage?chat_id={self.chat_id}&text={text}")
