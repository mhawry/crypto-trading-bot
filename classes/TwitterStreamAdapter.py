import requests


class TwitterStreamAdapter:
    """Twitter Stream API adapter"""

    USER_AGENT = "v2FilteredStreamPython"

    TWITTER_API_V2_STREAM_RULES_ENDPOINT = "https://api.twitter.com/2/tweets/search/stream/rules"

    TWITTER_API_V2_STREAM_ENDPOINT = "https://api.twitter.com/2/tweets/search/stream?expansions=attachments.media_keys&media.fields=type,url"

    def __init__(self, bearer_token: str) -> None:
        self.bearer_token = bearer_token

    def get_headers(self, r: requests.models.PreparedRequest) -> requests.models.PreparedRequest:
        """
        Add Authorization and User-Agent headers to a request.

        :param r: A PreparedRequest object.
        :return: The same PreparedRequest object with the Authorization and User-Agent headers added.
        """
        r.headers['Authorization'] = f"Bearer {self.bearer_token}"
        r.headers['User-Agent'] = self.USER_AGENT

        return r

    def get_rules(self) -> dict:
        """
        Get the current rules for the filtered stream endpoint.

        :return: The current rules for the filtered Stream endpoint.
        :raise Exception: If Twitter returns a status code other than 200.
        """
        response = requests.get(url=self.TWITTER_API_V2_STREAM_RULES_ENDPOINT,
                                auth=self.get_headers)

        if response.status_code != 200:
            raise Exception(f"Cannot get rules: {response.text} [{response.status_code}]")

        return response.json()

    def delete_all_rules(self, rules: dict) -> None:
        """
        Delete rules for the filtered stream endpoint.

        :param rules: The rules that need to be deleted.
        :raise Exception: If the rules cannot be deleted.
        """
        if rules is None or 'data' not in rules:
            return None

        ids = list(map(lambda rule: rule['id'], rules['data']))
        payload = {'delete': {'ids': ids}}
        response = requests.post(url=self.TWITTER_API_V2_STREAM_RULES_ENDPOINT,
                                 auth=self.get_headers,
                                 json=payload)

        if response.status_code != 200:
            raise Exception(f"Cannot delete rules: {response.text} [{response.status_code}]")

    def add_rules(self, rules: list) -> None:
        """
        Add rules for the filtered stream endpoint.

        :param rules: The rules that need to be added.
        :raise Exception: If the rules cannot be added.
        """
        payload = {'add': rules}
        response = requests.post(url=self.TWITTER_API_V2_STREAM_RULES_ENDPOINT,
                                 auth=self.get_headers,
                                 json=payload)

        if response.status_code != 201:
            raise Exception(f"Cannot add rules: {response.text} [{response.status_code}]")
