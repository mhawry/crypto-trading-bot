import requests


class TwitterStreamAdapter:
    """Twitter Stream API adapter"""

    TWITTER_API_V2_STREAM_RULES_ENDPOINT = "https://api.twitter.com/2/tweets/search/stream/rules"

    TWITTER_API_V2_STREAM_ENDPOINT = "https://api.twitter.com/2/tweets/search/stream?expansions=attachments.media_keys&media.fields=type,url"

    def __init__(self, bearer_token: str) -> None:
        self.bearer_token = bearer_token

    def get_headers(self, r: requests.models.PreparedRequest) -> requests.models.PreparedRequest:
        """Method required by bearer token authentication.

        Returns
        -------
        requests.models.PreparedRequest
            the HTTP request
        """
        r.headers['Authorization'] = f"Bearer {self.bearer_token}"
        r.headers['User-Agent'] = "v2FilteredStreamPython"

        return r

    def get_rules(self) -> dict:
        """Get existing rules for the Filtered stream Twitter API

        Returns
        -------
        dict
            a dict containing the Twitter rules

        Raises
        ------
        Exception
            If the API won't return the rules (HTTP status code other than 200).
        """
        response = requests.get(url=self.TWITTER_API_V2_STREAM_RULES_ENDPOINT,
                                auth=self.get_headers)

        if response.status_code != 200:
            raise Exception(f"Cannot get rules: {response.text} [{response.status_code}]")

        return response.json()

    def delete_all_rules(self, rules: dict) -> None:
        """Get existing rules for the Filtered stream Twitter API

        Parameters
        ----------
        rules : dict
            A dict containing the Twitter rules to delete.

        Raises
        ------
        Exception
            If the rules can't be deleted.
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
        """Add rules for the Filtered stream Twitter API

        Parameters
        ----------
        rules : list
            A dict containing the Twitter rules to add.

        Raises
        ------
        Exception
            If the API won't add the rules (HTTP status code other than 201).
        """
        payload = {'add': rules}
        response = requests.post(url=self.TWITTER_API_V2_STREAM_RULES_ENDPOINT,
                                 auth=self.get_headers,
                                 json=payload)

        if response.status_code != 201:
            raise Exception(f"Cannot add rules: {response.text} [{response.status_code}]")
