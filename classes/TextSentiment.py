import json
import requests


class TextSentiment:
    """Text Sentiment API wrapper"""

    def __init__(self, api_key: str) -> None:
        self.headers = {
            'x-rapidapi-key': api_key,
            'x-rapidapi-host': "text-sentiment.p.rapidapi.com"
        }

    def analyse(self, text: str) -> str:
        """Analyse sentiment

        :param text: Text to analyse.
        :rtype: str
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        response = requests.post(
            "https://text-sentiment.p.rapidapi.com/analyze",
            headers=self.headers,
            data={'text': text}
        )

        if response.status_code != 200:
            raise Exception(f"Cannot analyse text sentiment (HTTP {response.status_code}): {response.text}")  # TODO update error message

        return json.loads(response.content)
