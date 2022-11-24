import requests


class TwitterStreamAdapter:
    """Twitter Stream API adapter"""

    def __init__(self, bearer_token: str) -> None:
        self.bearer_token = bearer_token

    def bearer_oauth(self, r: requests.models.PreparedRequest) -> requests.models.PreparedRequest:
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
        """Get existing rules for the Filtered Stream Twitter API

        Returns
        -------
        dict
            a dict containing the Twitter rules

        Raises
        ------
        Exception
            If the API won't return the rules (HTTP status code other than 200).
        """
        response = requests.get(url="https://api.twitter.com/2/tweets/search/stream/rules",
                                auth=self.bearer_oauth)

        if response.status_code != 200:
            raise Exception(f"Cannot get rules: {response.text} [{response.status_code}]")

        return response.json()

    def delete_all_rules(self, rules: dict) -> None:
        """Get existing rules for the Filtered Stream Twitter API

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
        response = requests.post(url="https://api.twitter.com/2/tweets/search/stream/rules",
                                 auth=self.bearer_oauth,
                                 json=payload)

        if response.status_code != 200:
            raise Exception(f"Cannot delete rules: {response.text} [{response.status_code}]")

    def add_rules(self, rules: list) -> None:
        """Add rules for the Filtered Stream Twitter API

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
        response = requests.post(url="https://api.twitter.com/2/tweets/search/stream/rules",
                                 auth=self.bearer_oauth,
                                 json=payload)

        if response.status_code != 201:
            raise Exception(f"Cannot add rules: {response.text} [{response.status_code}]")

    def get_stream(self):
        """Start the Filtered API stream

        Raises
        ------
        Exception
            If the API Filtered Stream won't start (HTTP status code other than 200).
        """
        response = requests.get(url="https://api.twitter.com/2/tweets/search/stream?expansions=attachments.media_keys&media.fields=type,url",
                                auth=self.bearer_oauth,
                                stream=True)

        return response
