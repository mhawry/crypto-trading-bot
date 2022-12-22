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

ELON_TWITTER_ID = 44196397  # Elon Musk's twitter id (will never change)

CONFIG_FILE_PATH = 'config.yml'

# AWS config
AWS_REGION = 'ap-northeast-1'
AWS_SECRET_NAME = 'WinterBermApiKeys'
AWS_SECRET_NAME_DEV = 'WinterBermApiKeys-dev'

# AWS keys from Secrets Manager
BINANCE_API_KEY_AWS_SECRET_KEY = 'binance_api_key'
BINANCE_API_SECRET_AWS_SECRET_KEY = 'binance_api_secret'
TWITTER_API_BEARER_TOKEN_AWS_SECRET_KEY = 'twitter_api_bearer_token'
TELEGRAM_API_TOKEN_AWS_SECRET_KEY = 'telegram_api_token'
TELEGRAM_CHAT_ID_AWS_SECRET_KEY = 'telegram_chat_id'

# Huggingface model for Doge detection:
# https://huggingface.co/domluna/vit-base-patch16-224-in21k-shiba-inu-detector
HUGGINGFACE_MODEL_ENDPOINT = 'doge-detection-endpoint'
HUGGINGFACE_MODEL_DOGE_BREED_NAME = 'Shiba Inu Dog'
HUGGINGFACE_MODEL_SCORE_THRESHOLD = 0.32

DEV_ONLY_RULE_TAG = 'dev-only'  # used to tag rules for testing
HAS_MEDIA_RULE_TAG = 'has-media'  # to use with rules that contain media


def load_config(config_file: str) -> dict:
    """Loads yaml config"""
    with open(config_file) as config_file:
        return yaml.load(config_file, Loader=yaml.FullLoader)


def get_aws_secrets(secret_name: str, region_name: str, session: boto3.Session) -> dict or None:
    """Retrieves secrets from AWS Secrets Manager

    Parameters
    ----------
    secret_name : str
        The secret name to retrieve
    region_name : str
        The AWS region to use
    session : boto3.Session
        The AWS session to use

    Returns
    -------
    dict|None
        a dict containing the retrieved secrets, or None if they can't be retrieved
    """
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name,
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:  # noqa
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


def image_contains_doge(img: str) -> bool:
    """Checks whether an image contains a doge (Shiba Dog) or not

    Parameters
    ----------
    img : str
        URL of the image to analyse
    """

    logging.info(f"Checking if the following contains a Doge: {img}")

    inference = huggingface_predictor.predict({'inputs': img})

    logging.info(f"Inference results: {inference}")

    # noinspection PyUnresolvedReferences
    first_match = inference[0]

    # we need the first match to be a Doge and its score to be over a certain threshold
    return first_match['label'] == HUGGINGFACE_MODEL_DOGE_BREED_NAME and first_match['score'] >= HUGGINGFACE_MODEL_SCORE_THRESHOLD


def launch_trade(pair: str) -> None:
    """Creates the necessary orders on Binance

    Parameters
    ----------
    pair : str
        The pair to trade (needs to match the symbol in Binance)
    """
    # extracting trading parameters from config
    try:
        leverage, allocation, limit_price_multiplier, stop_loss_multiplier, take_profit_activation_multiplier, take_profit_callback_rate, tick_size, quantity_precision = itemgetter('leverage', 'allocation', 'limit_price_multiplier', 'stop_loss_multiplier', 'take_profit_activation_multiplier', 'take_profit_callback_rate', 'tick_size', 'quantity_precision')(trade_config[pair])
    except KeyError as e:  # noqa
        logging.error(f"Missing key in config for {pair}: {e}")
        sys.exit()

    logging.info(f"Launching trade for {pair}")

    position_info = binance.get_position_information(pair)

    # only change the leverage if it isn't already set (saves us an API call)
    # position_info['leverage'] is returned as a string
    if int(position_info['leverage']) != leverage:
        binance.set_leverage(pair, leverage)
        logging.info(f"Leverage set to {leverage}:1")

    # we don't want to buy if we're already long
    if float(position_info['positionAmt']) > 0:
        logging.info("We are already in a trade, do nothing")
        return

    # calculate the amount we want to buy
    quantity = round((float(margin_balance)*allocation*leverage)/float(position_info['markPrice']), quantity_precision)

    # if we reach this point it means we're ready to place the orders
    # using the current ask price times a multiplier as the limit price
    limit_price = round_step_size(binance.get_ask_price(pair)*limit_price_multiplier, tick_size)

    logging.info(f"Placing BUY LIMIT order for {quantity} {pair} at {limit_price}")

    try:
        order_id = binance.buy_limit(pair, quantity, limit_price)['orderId']
        order = binance.get_order(pair, order_id)
    except Exception as e:  # noqa
        logging.error(e)
        telegram.send_message(telegram_chat_id, "WARNING buy order execution broke")  # notification in case the program crashes
        return

    # making sure the order is filled before we move on to the stop orders
    if order['status'] == ORDER_STATUS_FILLED:
        logging.info(f"BUY LIMIT order #{order['orderId']} filled at {order['price']}")
        filled_price = float(order['price'])  # order['price'] is returned as a string
    else:
        logging.error(f"BUY LIMIT order #{order['orderId']} has NOT been filled: {order}")
        return

    buy_order_limit_price = order['price']  # we need this for the alert later

    # stop-loss
    stop_price = round_step_size(filled_price*stop_loss_multiplier, tick_size)
    logging.info(f"Placing SELL STOP order for {quantity} {pair} at {stop_price}")
    try:
        order = binance.set_stop_loss(pair, quantity, stop_price)
    except Exception as e:  # noqa
        logging.error(e)
        telegram.send_message(telegram_chat_id, "WARNING stop-loss order execution broke")  # notification in case the program crashes
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL STOP order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL STOP #{order['orderId']} has NOT been placed: {order}")

    # trailing-stop
    activation_price = round_step_size(filled_price*take_profit_activation_multiplier, tick_size)
    logging.info(f"Placing {take_profit_callback_rate}% TRAILING STOP order for {quantity} {pair} at {activation_price}")
    try:
        order = binance.set_trailing_stop(pair, quantity, activation_price, take_profit_callback_rate)
    except Exception as e:  # noqa
        logging.error(e)
        telegram.send_message(telegram_chat_id, "WARNING trailing-stop order execution broke")  # notification in case the program crashes
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"{take_profit_callback_rate}% TRAILING STOP order #{order['orderId']} placed at {activation_price}")
    else:
        logging.error(f"TRAILING STOP order #{order['orderId']} has NOT been placed: {order}")

    telegram.send_message(telegram_chat_id, f"Bough {quantity} {pair} at {buy_order_limit_price}")


class TwitterStream(TwitterStreamAdapter):
    def get_stream(self):
        try:
            with requests.get(url=self.TWITTER_API_V2_STREAM_ENDPOINT, auth=self.get_headers, stream=True) as response:
                # stream has been disconnected, wait until it resets
                if response.status_code == 429:
                    logging.warning(f"Twitter stream disconnected [{response.status_code}]: {response.text or response.reason}")

                    # Twitter gives us the timestamp from which we'll be able to reconnect
                    reset = float(response.headers['x-rate-limit-reset'])+1
                    logging.info(f"Waiting until {reset}")
                    time.sleep(reset-time.time())

                    # we should be good to go now
                    self.get_stream()
                elif response.status_code != 200:
                    raise Exception(f"Unknown Twitter stream error [{response.status_code}]: {response.text}")

                logging.info("Twitter stream running successfully")

                for response_line in response.iter_lines():
                    if response_line:
                        json_response = json.loads(response_line)

                        if 'data' not in json_response:
                            logging.warning(f"Invalid response from Twitter stream API: {json_response}")
                            continue

                        tweet = json_response['data']

                        # if a tweet mentions more than one trading pair we need to pick only one, hence using 0 as the index
                        tag = json_response['matching_rules'][0]['tag']

                        logging.info(f"Analysing tweet {tweet['id']} with tag {tag}")

                        if tag == DEV_ONLY_RULE_TAG:
                            logging.info(f"Tweet {tweet['id']} tagged as dev only, skipping")
                            continue

                        if tag != HAS_MEDIA_RULE_TAG:
                            # at this stage the tag will be a trading pair
                            logging.info(f"Tweet {tweet['id']} found for {tag} trading pair")

                            thread = threading.Thread(target=launch_trade, args=(tag, ))
                            thread.start()
                            thread.join()

                        # special use case for when there is a tweet with a Doge
                        if tag == HAS_MEDIA_RULE_TAG and 'includes' in json_response:
                            doge_found = False
                            for media in json_response['includes']['media']:
                                if media['type'] == 'photo':
                                    if image_contains_doge(media['url']):
                                        doge_found = True
                                        break

                            if doge_found:
                                logging.info(f"Tweet {tweet['id']} contains a Doge, launching trade")

                                thread = threading.Thread(target=launch_trade, args=('DOGEUSDT', ))
                                thread.start()
                                thread.join()
        except Exception as e:  # noqa
            logging.error(e)
            self.get_stream()


# logging config with milliseconds (important)
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)

logging.info("Program started")

parser = argparse.ArgumentParser(description="Trigger crypto trades based on Elon Musk's tweets")
parser.add_argument('--dry-run',
                    action='store_true',
                    help="Use Binance testnet")
parser.add_argument('--skip-rules',
                    action='store_true',
                    help="Use this if the Twitter rules are already set and don't need to be updated")

args = parser.parse_args()

if args.dry_run:
    logging.info("Using test credentials")
    aws_secret_name = AWS_SECRET_NAME_DEV
else:
    logging.warning("USING PRODUCTION CREDENTIALS")
    aws_secret_name = AWS_SECRET_NAME

    # never skip rules when using production credentials
    if args.skip_rules:
        logging.warning("Overriding skip-rules")
        args.skip_rules = False

# preloading the config to save time when we're ready to trade
config = load_config(CONFIG_FILE_PATH)
try:
    trade_config = config['trading_pairs']['dev'] if args.dry_run else config['trading_pairs']['prod']
except KeyError as e:
    logging.error(f"Error loading config: {e}")
    sys.exit()

aws_session = boto3.session.Session()

try:
    aws_secrets = get_aws_secrets(aws_secret_name, AWS_REGION, aws_session)
except Exception as e:
    logging.error(f"Unable to pull secrets from AWS Secrets Manager: {e}")
    sys.exit()

# unpack the API keys
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
    telegram = TelegramAdapter(token=telegram_api_token)
except Exception as e:
    logging.error(f"Telegram API error: {e}")
    sys.exit()

huggingface_predictor = HuggingFacePredictor(endpoint_name=HUGGINGFACE_MODEL_ENDPOINT, sagemaker_session=aws_session)

# will be updated in main()
margin_balance = 0.0


def main():
    rules = []
    for symbol, pair_config in trade_config.items():
        # we're pulling the tick size here and adding it to the local config
        # this improves latency by "saving" an API call before placing the orders
        trade_config[symbol]['tick_size'] = binance.get_tick_size(symbol)
        trade_config[symbol]['quantity_precision'] = binance.get_quantity_precision(symbol)

        rule = {
            'value': '(' + ' OR '.join(pair_config['keywords']) + f') from:{ELON_TWITTER_ID} -is:retweet -is:reply',
            # for testing
            # 'value': '(' + ' OR '.join(pair_config['keywords']) + ') -is:retweet -is:reply',
            'tag': symbol  # we'll use the symbol as a tag, this way we'll know which symbol triggered the trade
        }
        rules.append(rule)

    # special rule for tweets that contain a Doge
    rules.append({
        'value': f'has:media from:{ELON_TWITTER_ID} -is:retweet -is:reply',
        'tag': HAS_MEDIA_RULE_TAG
    })

    # for testing
    # rules.append({
    #     'value': f'bitcoin -from:{ELON_TWITTER_ID} -is:retweet -is:reply',
    #     'tag': DEV_ONLY_RULE_TAG
    # })

    global margin_balance
    margin_balance = binance.get_margin_balance()

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

    logging.info("Starting Twitter stream")

    twitter_stream.get_stream()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Program terminated")
        sys.exit(0)
