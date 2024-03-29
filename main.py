import sys
import logging
import json
import time
import requests
import yaml
import threading
import argparse
import boto3
from operator import itemgetter
from binance.enums import *
from binance.helpers import round_step_size
from binance.exceptions import BinanceAPIException
from botocore.exceptions import ClientError
from classes.BinanceFuturesAdapter import BinanceFuturesAdapter
from classes.TwitterStreamAdapter import TwitterStreamAdapter
from classes.TelegramAdapter import TelegramAdapter
from sagemaker.huggingface import HuggingFacePredictor

CONFIG_FILE_PATH = 'config.yml'

# AWS config
AWS_REGION = 'ap-northeast-1'
AWS_SECRET_KEY = 'CryptoTradingBotApiKeys'

# Names of the secret keys used in AWS Secrets Manager.
BINANCE_API_KEY_AWS_SECRET_KEY = 'binance_api_key'
BINANCE_API_SECRET_AWS_SECRET_KEY = 'binance_api_secret'
TWITTER_API_BEARER_TOKEN_AWS_SECRET_KEY = 'twitter_api_bearer_token'
TELEGRAM_API_TOKEN_AWS_SECRET_KEY = 'telegram_api_token'
TELEGRAM_CHAT_ID_AWS_SECRET_KEY = 'telegram_chat_id'

DOGE_SYMBOL = 'DOGEUSDT'

# Huggingface model for Doge detection:
# https://huggingface.co/domluna/vit-base-patch16-224-in21k-shiba-inu-detector
HUGGINGFACE_MODEL_ENDPOINT = 'doge-detection-endpoint'
HUGGINGFACE_MODEL_DOGE_BREED_NAME = 'Shiba Inu Dog'
HUGGINGFACE_MODEL_SCORE_THRESHOLD = 0.32

DEV_ONLY_RULE_TAG = 'dev-only'
HAS_MEDIA_RULE_TAG = 'has-media'


def load_config(config_file: str) -> dict:
    """Load yaml config"""
    with open(config_file) as config_file:
        return yaml.load(config_file, Loader=yaml.FullLoader)


def get_aws_secret(secret_name: str, region_name: str) -> dict:
    """
    Retrieve a secret from AWS Secrets Manager.

    :param secret_name: The name of the secret to retrieve.
    :param region_name: The AWS region to use.
    :return: The retrieved secret value.
    :raise ClientError: If there is an error retrieving the secret.
    """
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name,
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name,
        )
    except ClientError as e:  # noqa
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    return json.loads(get_secret_value_response['SecretString'])


def image_contains_doge(img_src: str) -> bool:
    """
    Check whether an image contains a Doge or not.

    :param img_src: URL of the image to analyse.
    :return: True if the image contains a Doge. False if it doesn't.
    """
    logging.info(f"Checking if the following contains a Doge: {img_src}")

    inference = huggingface_predictor.predict({'inputs': img_src})

    logging.info(f"Inference results: {inference}")

    # noinspection PyUnresolvedReferences
    first_match = inference[0]

    # We need the first match to be a Doge and its score to be over a certain threshold.
    return first_match['label'] == HUGGINGFACE_MODEL_DOGE_BREED_NAME and first_match['score'] >= HUGGINGFACE_MODEL_SCORE_THRESHOLD


def launch_trade(symbol: str) -> None:
    """
    Create the necessary orders on Binance.

    :param symbol: The symbol to create the orders for.
    """
    # Extract the trading parameters from the config.
    try:
        leverage, allocation, limit_price_multiplier, stop_loss_multiplier, take_profit_activation_multiplier, take_profit_callback_rate, tick_size, quantity_precision = itemgetter('leverage', 'allocation', 'limit_price_multiplier', 'stop_loss_multiplier', 'take_profit_activation_multiplier', 'take_profit_callback_rate', 'tick_size', 'quantity_precision')(trade_config[symbol])  # noqa
    except KeyError as e:  # noqa
        logging.error(f"Missing key in config for {symbol}: {e}")
        sys.exit()

    margin_balance = binance.get_margin_balance()

    logging.info(f"Launching trade for {symbol}. Margin balance: ${round(margin_balance, 2)}.")

    position_info = binance.get_position_information(symbol)

    # Only set the leverage if it isn't already set (saves an API call).
    if int(position_info['leverage']) != leverage:
        binance.set_leverage(symbol, leverage)
        logging.info(f"Leverage set to {leverage}:1")

    # Make sure we're not already long.
    if float(position_info['positionAmt']) > 0:
        logging.info("We are already in a trade, do nothing")
        return

    quantity = round((float(margin_balance)*allocation*leverage)/float(position_info['markPrice']), quantity_precision)

    # We're ready to place the orders.
    limit_price = round_step_size(binance.get_ask_price(symbol) * limit_price_multiplier, tick_size)

    telegram.send_message(f"Buying {quantity} {symbol} at {limit_price}")

    logging.info(f"Placing BUY LIMIT order for {quantity} {symbol} at {limit_price}")

    try:
        order_id = binance.buy_limit(symbol, quantity, limit_price)['orderId']
        order = binance.get_order(symbol, order_id)
    except Exception as e:  # noqa
        telegram.send_message("BUY LIMIT order execution exception, see logs for details")
        logging.error(e)
        return

    # Make sure the order is filled before moving on to the stop orders.
    if order['status'] == ORDER_STATUS_FILLED:
        logging.info(f"BUY LIMIT order #{order['orderId']} filled at {order['price']}")
        filled_price = float(order['price'])  # order['price'] is returned as a string
    else:
        logging.error(f"BUY LIMIT order #{order['orderId']} has NOT been filled: {order}")
        return

    buy_order_limit_price = order['price']

    # This is the stop-loss order.
    stop_price = round_step_size(filled_price*stop_loss_multiplier, tick_size)
    logging.info(f"Placing SELL STOP order for {quantity} {symbol} at {stop_price}")
    try:
        order = binance.set_stop_loss(symbol, quantity, stop_price)
    except Exception as e:  # noqa
        telegram.send_message("SELL STOP order execution exception, see logs for details")
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL STOP order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL STOP order #{order['orderId']} has NOT been placed: {order}")

    # This is the trailing stop order.
    activation_price = round_step_size(filled_price*take_profit_activation_multiplier, tick_size)
    logging.info(f"Placing {take_profit_callback_rate}% TRAILING STOP order for {quantity} {symbol} at {activation_price}")
    try:
        order = binance.set_trailing_stop(symbol, quantity, activation_price, take_profit_callback_rate)
    except Exception as e:  # noqa
        telegram.send_message("TRAILING STOP order execution exception, see logs for details")
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"{take_profit_callback_rate}% TRAILING STOP order #{order['orderId']} placed at {activation_price}")
    else:
        logging.error(f"TRAILING STOP order #{order['orderId']} has NOT been placed: {order}")

    telegram.send_message(f"Bought {quantity} {symbol} at {buy_order_limit_price}")


class TwitterStream(TwitterStreamAdapter):
    def get_stream(self):
        try:
            with requests.get(url=self.TWITTER_API_V2_STREAM_ENDPOINT, auth=self.get_headers, stream=True) as response:
                # 429 means the stream has been disconnected.
                if response.status_code == 429:
                    logging.warning(f"Twitter stream disconnected [{response.status_code}]: {response.text or response.reason}")

                    # Twitter gives us the timestamp from which we'll be able to reconnect.
                    reset = int(response.headers['x-rate-limit-reset']) + 1
                    logging.info(f"Waiting until {reset}")
                    time.sleep(reset - time.time())
                    self.get_stream()
                elif response.status_code != 200:
                    raise Exception(f"Unknown Twitter stream error [{response.status_code}]: {response.text}")

                logging.info("Twitter stream running successfully")

                try:
                    for response_line in response.iter_lines(decode_unicode=True):
                        # Twitter sends a keep alive heartbeat every 20 seconds.
                        if response_line == b'':
                            continue

                        if response_line:
                            json_response = json.loads(response_line)

                            if 'data' not in json_response:
                                logging.warning(f"Invalid response from Twitter stream API: {json_response}")
                                continue

                            tweet = json_response['data']

                            # The tag from the matching rule is the symbol.
                            # Note: it's possible for a tweet to contain more than one symbol. We only trade one symbol at a time, so we use index 0 to get the first symbol mentioned in the tweet.
                            tag = json_response['matching_rules'][0]['tag']

                            logging.info(f"Analysing tweet {tweet['id']} with tag {tag}")

                            if tag == DEV_ONLY_RULE_TAG:
                                logging.info(f"Tweet {tweet['id']} tagged as dev only, skipping")
                                continue

                            if tag != HAS_MEDIA_RULE_TAG:
                                telegram.send_message(f"Triggering trade for {tag} based on tweet id {tweet['id']}")

                                logging.info(f"Tweet id {tweet['id']} found for {tag} symbol")

                                thread = threading.Thread(target=launch_trade, args=(tag, ))
                                thread.start()
                                thread.join()

                            # Special use case for when a tweet contains the image of a Doge.
                            if tag == HAS_MEDIA_RULE_TAG and 'includes' in json_response:
                                doge_found = False
                                for media in json_response['includes']['media']:
                                    if media['type'] == 'photo':
                                        if image_contains_doge(media['url']):
                                            doge_found = True
                                            break

                                if doge_found:
                                    telegram.send_message(f"Triggering DOGE trade based on media from tweet id {tweet['id']}")

                                    logging.info(f"Tweet id {tweet['id']} contains a Doge, launching trade")

                                    thread = threading.Thread(target=launch_trade, args=('DOGEUSDT', ))
                                    thread.start()
                                    thread.join()
                except Exception as e:  # noqa
                    response.close()
                    raise Exception(e)
        except Exception as e:  # noqa
            logging.error(e)
            self.get_stream()


# Logging config with milliseconds (important).
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)

logging.info("Program started")

parser = argparse.ArgumentParser(description="Trigger crypto trades based on tweets from supplied list of account ids")
parser.add_argument('--dry-run',
                    action='store_true',
                    help="Use Binance testnet")
parser.add_argument('--skip-rules',
                    action='store_true',
                    help="Use this if the Twitter rules are already set and don't need to be updated")

args = parser.parse_args()

if args.dry_run:
    logging.info("Using test credentials")
    aws_secret_name = f"dev/{AWS_SECRET_KEY}"
else:
    logging.warning("USING PRODUCTION CREDENTIALS")
    aws_secret_name = f"prod/{AWS_SECRET_KEY}"

    # Never skip rules when using production credentials.
    if args.skip_rules:
        logging.warning("Overriding skip-rules")
        args.skip_rules = False

# Preload the config to save time when we need to place the trades.
config = load_config(CONFIG_FILE_PATH)
try:
    trade_config = config['symbols']['dev'] if args.dry_run else config['symbols']['prod']
except KeyError as e:
    logging.error(f"Error loading config: {e}")
    sys.exit()

try:
    aws_secrets = get_aws_secret(aws_secret_name, AWS_REGION)
except Exception as e:
    logging.error(f"Unable to pull secrets from AWS Secrets Manager: {e}")
    sys.exit()

# Unpack the API keys.
try:
    binance_api_key, binance_api_secret, twitter_api_bearer_token, telegram_api_token, telegram_chat_id = itemgetter(BINANCE_API_KEY_AWS_SECRET_KEY, BINANCE_API_SECRET_AWS_SECRET_KEY, TWITTER_API_BEARER_TOKEN_AWS_SECRET_KEY, TELEGRAM_API_TOKEN_AWS_SECRET_KEY, TELEGRAM_CHAT_ID_AWS_SECRET_KEY)(aws_secrets)
except KeyError as e:
    logging.error(f"Missing AWS secret key: {e}")
    sys.exit()

try:
    binance = BinanceFuturesAdapter(
        api_key=binance_api_key,
        api_secret=binance_api_secret,
        test=args.dry_run
    )
except BinanceAPIException as e:
    logging.error(f"Binance API error: {e.message} [{e.status_code}]")
    sys.exit()

try:
    telegram = TelegramAdapter(token=telegram_api_token, chat_id=telegram_chat_id)
except Exception as e:
    logging.error(f"Telegram API error: {e}")
    sys.exit()

huggingface_predictor = HuggingFacePredictor(endpoint_name=HUGGINGFACE_MODEL_ENDPOINT)


def main():
    rules = []
    for symbol, symbol_config in trade_config.items():
        # Pull the tick size here and add it to the local config.
        # This improves latency by "saving" an API call when it's time to place the trades.
        trade_config[symbol]['tick_size'] = binance.get_tick_size(symbol)
        trade_config[symbol]['quantity_precision'] = binance.get_quantity_precision(symbol)

        keywords = ' OR '.join(symbol_config['keywords'])
        twitter_ids = ' OR '.join(['from:' + str(twitter_id) for twitter_id in symbol_config['twitter_ids']])

        rule = {
            'value': f"({keywords}) ({twitter_ids}) -is:retweet -is:reply",
            'tag': symbol  # Use the symbol as a tag. This will come in handy when it's time to place the trades.
        }
        rules.append(rule)

        # Special rule for tweets that contain the image of a Doge.
        if symbol == DOGE_SYMBOL:
            rules.append({
                'value': f"has:media ({twitter_ids}) -is:retweet -is:reply",
                'tag': HAS_MEDIA_RULE_TAG
            })

    # for testing
    # rules.append({
    #     'value': f"bitcoin ({accounts}) -is:retweet -is:reply",
    #     'tag': DEV_ONLY_RULE_TAG
    # })

    twitter_stream = TwitterStream(twitter_api_bearer_token)

    if args.skip_rules is False:
        logging.info("Retrieving current rules")
        current_rules = twitter_stream.get_rules()
        logging.info("Removing existing rules")
        twitter_stream.delete_all_rules(current_rules)
        logging.info("Setting up new rules")
        twitter_stream.add_rules(rules)
        logging.info("New rules have been set")
    else:
        logging.warning("Using existing Twitter rules")

    telegram.send_message(f"Program running successfully")

    logging.info("Starting Twitter stream")

    twitter_stream.get_stream()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Program terminated")
        sys.exit(0)
