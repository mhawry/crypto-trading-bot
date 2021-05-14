import json
import requests


class TwitterStream:
    """Twitter Stream API wrapper"""

    def __init__(self, bearer_token: str) -> None:
        self.headers = {'Authorization': f"Bearer {bearer_token}"}

    def get_rules(self) -> dict:
        """Get current Twitter Stream rules

        :rtype: dict
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        response = requests.get(
            "https://api.twitter.com/2/tweets/search/stream/rules",
            headers=self.headers
        )

        if response.status_code != 200:
            raise Exception(f"Cannot get rules (HTTP {response.status_code}): {response.text}")

        return response.json()

    def delete_rules(self, rules: dict) -> dict:
        """Delete a set of Twitter Stream rules

        :param rules: Rules to be deleted.
        :rtype: dict
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        if rules is None or 'data' not in rules:
            return {}

        ids = list(map(lambda rule: rule['id'], rules['data']))
        payload = {'delete': {'ids': ids}}
        response = requests.post(
            "https://api.twitter.com/2/tweets/search/stream/rules",
            headers=self.headers,
            json=payload
        )

        if response.status_code != 200:
            raise Exception(f"Cannot delete rules (HTTP {response.status_code}): {response.text}")

        print(json.dumps(response.json()))

    def set_rules(self, rules: list) -> None:
        """Set Twitter Stream rules

        :param rules: Rules to be set.
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        payload = {'add': rules}
        response = requests.post(
            "https://api.twitter.com/2/tweets/search/stream/rules",
            headers=self.headers,
            json=payload
        )

        if response.status_code != 201:
            raise Exception(f"Cannot add rules (HTTP {response.status_code}): {response.text}")

    def get_stream(self) -> dict:
        """Start the stream

        :rtype: dict
        :raises Exception: If the response from the API isn't 200. TODO update this comment
        """

        response = requests.get(
            "https://api.twitter.com/2/tweets/search/stream",
            headers=self.headers,
            stream=True
        )

        if response.status_code != 200:
            raise Exception(f"Cannot get stream (HTTP {response.status_code}): {response.text}")

        for response_line in response.iter_lines():
            if response_line:
                return json.loads(response_line)
