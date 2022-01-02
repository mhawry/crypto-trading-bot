import logging
import json
import yaml
import tweepy
import threading
import boto3
from botocore.exceptions import ClientError
from nltk.sentiment import SentimentIntensityAnalyzer
from classes.BinanceFuturesAdapter import BinanceFuturesAdapter
from binance.enums import *

ELON_TWITTER_ID = 44196397  # Elon Musk's twitter id (will never change)

CONFIG_FILE_PATH = 'config.yml'

# a configuration for the symbol must exist in the config file
# TODO make this work with multiple symbols
SYMBOL = 'BTCUSDT'

# compound threshold that will trigger a trade
SENTIMENT_COMPOUND_THRESHOLD = 0.5

# AWS config
AWS_REGION = 'ca-central-1'
AWS_SECRET_NAME = 'WinterBermApiKeys'

# AWS keys from Secrets Manager
BINANCE_API_KEY_AWS_SECRET_KEY = 'binance_api_key'
BINANCE_API_SECRET_AWS_SECRET_KEY = 'binance_api_secret'
TWITTER_CONSUMER_KEY_AWS_SECRET_KEY = 'twitter_consumer_key'
TWITTER_CONSUMER_SECRET_AWS_SECRET_KEY = 'twitter_consumer_secret'
TWITTER_ACCESS_TOKEN_AWS_SECRET_KEY = 'twitter_access_token'
TWITTER_ACCESS_TOKEN_SECRET_AWS_SECRET_KEY = 'twitter_access_token_secret'


def load_config(config_file: str) -> dict:
    """Load yaml config file and returns dict

    :param config_file: Path to the yaml config file
    :rtype dict
    """
    with open(config_file) as config_file:
        return yaml.load(config_file, Loader=yaml.FullLoader)


def get_aws_secrets(secret_name: str, region_name: str) -> dict or None:
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name,
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logging.error(f"The requested secret {secret_name} was not found")
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            logging.error(f"The request was invalid due to: {e}")
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            logging.error(f"The request had invalid params: {e}")
        elif e.response['Error']['Code'] == 'DecryptionFailure':
            logging.error(f"The requested secret can't be decrypted using the provided KMS key: {e}")
        elif e.response['Error']['Code'] == 'InternalServiceError':
            logging.error(f"An error occurred on service side: {e}")
    else:
        # Secrets Manager decrypts the secret value using the associated KMS CMK
        # Depending on whether the secret was a string or binary, only one of these fields will be populated
        if 'SecretString' in get_secret_value_response:
            return json.loads(get_secret_value_response['SecretString'])

    return


def get_sentiment(tweet):
    sia = SentimentIntensityAnalyzer()
    return sia.polarity_scores(tweet)


def buy():
    config = load_config(CONFIG_FILE_PATH)

    # making sure we have all the right config variables
    try:
        trade_config = config['TRADING_PAIRS'][SYMBOL]
        leverage = trade_config['LEVERAGE']
        quantity = trade_config['QUANTITY']
        stop_loss_multiplier = trade_config['STOP_LOSS_MULTIPLIER']
        take_profit_multiplier = trade_config['TAKE_PROFIT_MULTIPLIER']
    except KeyError as e:
        logging.error(f"Key missing from config: {e}")
        return

    binance = BinanceFuturesAdapter(
        api_key=aws_secrets[BINANCE_API_KEY_AWS_SECRET_KEY],
        api_secret=aws_secrets[BINANCE_API_SECRET_AWS_SECRET_KEY],
        symbol=SYMBOL,
        leverage=leverage,
        test=True
    )

    binance.set_one_way_position_mode()

    # we don't want to buy if we're already long
    if binance.get_position_amount() != 0:
        logging.info("We are already in a trade, do nothing")
        return

    # to be safe, we don't want to buy if there are already open orders on the symbol
    if binance.get_open_orders():
        logging.info("There are already open orders on this symbol, do nothing")
        return

    # if we reach this point it means we're ready to buy
    # using the current ask price as the limit price
    # TODO should we really do this? need to double-check
    # why convert to float?
    limit_price = float(binance.get_ticker_data()['askPrice'])

    logging.info(f"Placing BUY LIMIT order for {quantity} {SYMBOL} at {limit_price}")

    try:
        order_id = binance.buy_limit(quantity, limit_price)['orderId']
    except Exception as e:
        logging.error(e)
        return

    order = binance.get_order(order_id)

    # making sure the order is filled before we move on to the stop orders
    if order['status'] == ORDER_STATUS_FILLED:
        logging.info(f"Limit order #{order['orderId']} filled at {order['price']}")
    else:
        logging.error(f"Limit order #{order['orderId']} has NOT been filled: {order}")
        return

    # at this point we are ready to set the stop loss
    stop_price = round(float(order['price'])*stop_loss_multiplier, 2)

    logging.info(f"Placing SELL STOP order for {quantity} {SYMBOL} at {stop_price}")

    try:
        order = binance.set_stop_loss(quantity, stop_price)
    except Exception as e:
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL STOP order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL STOP #{order['orderId']} has NOT been placed: {order}")

    # at this point we are ready to set the trailing stop
    stop_price = round(limit_price*take_profit_multiplier, 2)

    logging.info(f"Placing SELL TAKE PROFIT order for {quantity} {SYMBOL} at {stop_price}")

    try:
        order = binance.set_take_profit(quantity, stop_price)
    except Exception as e:
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL STOP order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL STOP #{order['orderId']} has NOT been placed: {order}")


class TwitterStream(tweepy.Stream):
    def on_status(self, status):
        logging.info(f"Tweet logged: {status.text}")

        sentiment = get_sentiment(status.text)

        # if the compound is above the threshold, buy
        if sentiment['compound'] >= SENTIMENT_COMPOUND_THRESHOLD:
            logging.info(f"Sentiment compound ({sentiment['compound']}) higher than threshold - triggering trade")

            thread = threading.Thread(target=buy)
            thread.start()
            thread.join()


# standard logging config
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)

# pull the secrets from AWS Secrets Manager
# TODO there may be a better way to do this and store them all in variables here
aws_secrets = get_aws_secrets(AWS_SECRET_NAME, AWS_REGION)


def main():
    logging.info("Program started")

    # shouldn't happen but just in case
    if aws_secrets is None:
        logging.error(f"Unable to pull secrets from AWS Secrets Manager [Secret name: {AWS_SECRET_NAME}; Region: {AWS_REGION}]. Exiting.")

        # we can't move forward without the creds
        exit()

    buy()
    exit()

    twitter_stream = TwitterStream(consumer_key=aws_secrets[TWITTER_CONSUMER_KEY_AWS_SECRET_KEY],
                                   consumer_secret=aws_secrets[TWITTER_CONSUMER_SECRET_AWS_SECRET_KEY],
                                   access_token=aws_secrets[TWITTER_ACCESS_TOKEN_AWS_SECRET_KEY],
                                   access_token_secret=aws_secrets[TWITTER_ACCESS_TOKEN_SECRET_AWS_SECRET_KEY])

    # rules = [
    #     {"value": f"(Bitcoin OR BTC) from:{ELON_TWITTER_ID} -is:retweet"},
    #     {"value": "bitcoin"}  # TODO for testing - remove later
    # ]

    twitter_stream.filter(track=["Bitcoin", "BTC", "Doge"], languages=["en"])
    twitter_stream.sample()

    # TODO will we ever reach this part?
    logging.info("Program stopped")


if __name__ == '__main__':
    main()
