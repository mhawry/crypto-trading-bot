import telegram


class Telegram:
    """Telegram API wrapper"""

    def __init__(self, token: str) -> None:
        self.bot = telegram.Bot(token=token)

    def post(self, chat_id: str, message: str) -> None:
        """Post a message to Telegram

        :param chat_id: ID of the chat room to post the message to
        :param message: Message to post
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        # TODO add error handling here
        self.bot.sendMessage(chat_id, message)
