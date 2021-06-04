from google.cloud import secretmanager
from nltk.sentiment import SentimentIntensityAnalyzer
from classes.TwitterStreamAdapter import TwitterStreamAdapter
from classes.TelegramAdapter import TelegramAdapter
from classes.BinanceFuturesAdapter import BinanceFuturesAdapter

GOOGLE_PROJECT_ID = 'winter-berm-302500'  # Google project id for Winter Berm
ELON_TWITTER_ID = 44196397  # Elon Musk's twitter id (will never change)

# secret names from Google Cloud - change them here if they are changed in GCP
TELEGRAM_CHAT_ID_SECRET_KEY = 'telegram-chat-id'
TELEGRAM_TOKEN_SECRET_KEY = 'telegram-token'
TWITTER_BEARER_TOKEN_SECRET_KEY = 'twitter-bearer-token'

# compound threshold that will trigger a trade
SENTIMENT_COMPOUND_THRESHOLD = 0.5

DOGE_SYMBOL = 'DOGEUSDT'
LEVERAGE = 20  # using 20x leverage which will give us a max position size of 25,000 USDT
DEFAULT_ALLOCATION = 0.9  # default percentage of available funds to use for trades

# BINANCE KEYS FOR PROD
BINANCE_API_KEY = 'lfqRViovtvFFdLgyMpyDsAURCD1qY9Az2X4659uh6CmMHX67D8bM037fi4m7DJF1'
BINANCE_API_SECRET = 'zSjZhQmdk7h8ogQvZDCnMzPh1kPIdFGz4COe8IAa9tR5lrFs1nh89QpeDCgGo7tM'

# BINANCE KEYS MAIN TESTNET - NO FUTURES
BINANCE_TESTNET_API_KEY = '7xizBlEccM7JTcAIREeF1WOnajHIHfrg0jHWvPTqW2JE5dMAQWH7fWSIQ55zdN3q'
BINANCE_TESTNET_API_SECRET = 'iMK0YAJdocdoG47ClkrVm3iIGrRocQdRRlTwYNCk8lGW7VOBCcupuOaKd9YI0zJ8'

# BINANCE KEYS FOR TESTNET WITH FUTURES
BINANCE_TESTNET_FUTURES_API_KEY = '3b4697e7e702c2e3b19f47b96d3903ead2b4874d4737af86261d4ac1d47cec48'
BINANCE_TESTNET_FUTURES_API_SECRET = 'd0bc528b73c37eb5b5972302ac78478606a487d4b5cbf9222a34317c331b5181'


def access_google_secret(project_id: str, secret_id: str) -> str:
    """
    Access the payload for the given secret version if one exists. The version
    can be a version number as a string (e.g. "5") or an alias (e.g. "latest").
    """

    client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    response = client.access_secret_version(request={'name': name})
    secret = response.payload.data.decode("UTF-8")

    return secret


def get_sentiment(text):
    sia = SentimentIntensityAnalyzer()
    return sia.polarity_scores(text)


def main():
    # binance = BinanceFuturesAdapter(
    #     api_key=BINANCE_API_KEY,
    #     api_secret=BINANCE_API_SECRET,
    #     symbol=DOGE_SYMBOL,
    #     test=False
    # )

    binance = BinanceFuturesAdapter(
        api_key=BINANCE_TESTNET_FUTURES_API_KEY,
        api_secret=BINANCE_TESTNET_FUTURES_API_SECRET,
        symbol=DOGE_SYMBOL,
        leverage=LEVERAGE,
        test=True
    )

    # test for buying coins
    mark_price = binance.get_mark_price()
    usdt_trade_size = binance.get_usdt_trade_size(DEFAULT_ALLOCATION)
    quantity = int(usdt_trade_size / mark_price)
    limit_price = round(mark_price*1.0015, 4)  # TODO move to a constant
    print(mark_price)
    print(usdt_trade_size)
    print(quantity)
    print(limit_price)
    # print(binance.buy(quantity, limit_price))
    exit()

    # we need a few API keys
    twitter_bearer_token = access_google_secret(GOOGLE_PROJECT_ID, TWITTER_BEARER_TOKEN_SECRET_KEY)
    telegram_token = access_google_secret(GOOGLE_PROJECT_ID, TELEGRAM_TOKEN_SECRET_KEY)
    telegram_chat_id = access_google_secret(GOOGLE_PROJECT_ID, TELEGRAM_CHAT_ID_SECRET_KEY)

    rules = [
        # {"value": f"(Bitcoin OR BTC) from:{ELON_TWITTER_ID} -is:retweet"},
        {"value": "bitcoin"}  # TODO for testing - remove later
    ]

    # instantiating the Twitter Stream adapter
    twitter_stream = TwitterStreamAdapter(twitter_bearer_token)
    twitter_stream.set_rules(rules)

    # instantiating the Telegram adapter
    telegram = TelegramAdapter(telegram_token)

    # start the stream
    tweet_object = twitter_stream.get_stream()

    # if we reach this part it means we have a tweet
    tweet = tweet_object['data']['text']
    sentiment = get_sentiment(tweet)

    # we don't trade if the compound is below the threshold
    if sentiment['compound'] < SENTIMENT_COMPOUND_THRESHOLD:
        telegram.post(telegram_chat_id, f"Ignoring tweet because of low compound: {tweet} [{sentiment['compound']}]")
        return

    telegram.post(telegram_chat_id, f"Following tweet will trigger a trade: {tweet} [{sentiment['compound']}]")


if __name__ == '__main__':
    main()
