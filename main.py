import sys
import logging
import json
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


def load_config(config_file: str) -> dict:
    """Loads yaml config"""
    with open(config_file) as config_file:
        return yaml.load(config_file, Loader=yaml.FullLoader)


def get_aws_secrets(secret_name: str, region_name: str) -> dict or None:
    """Retrieves secrets from AWS Secrets Manager

    Parameters
    ----------
    secret_name : str
        The secret name to retrieve
    region_name : str
        The AWS region to use

    Returns
    -------
    dict|None
        a dict containing the retrieved secrets, or None if they can't be retrieved
    """
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


def launch_trade(pair: str) -> None:
    """Creates the necessary orders on Binance

    Parameters
    ----------
    pair : str
        The pair to trade (needs to match the symbol in Binance)
    """
    # extracting trading parameters from config
    leverage, quantity, stop_loss_multiplier, take_profit_multiplier, limit_price_multiplier, tick_size = itemgetter('leverage', 'quantity', 'stop_loss_multiplier', 'take_profit_multiplier', 'limit_price_multiplier', 'tick_size')(trade_config[pair])

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

    # if we reach this point it means we're ready to place the orders
    # using the current ask price times a multiplier as the limit price
    limit_price = round_step_size(binance.get_ask_price(pair)*limit_price_multiplier, tick_size)

    logging.info(f"Placing BUY LIMIT order for {quantity} {pair} at {limit_price}")

    try:
        order_id = binance.buy_limit(pair, quantity, limit_price)['orderId']
    except Exception as e:
        logging.error(e)
        return

    order = binance.get_order(pair, order_id)

    # making sure the order is filled before we move on to the stop orders
    if order['status'] == ORDER_STATUS_FILLED:
        logging.info(f"BUY LIMIT order #{order['orderId']} filled at {order['price']}")
        filled_price = float(order['price'])  # order['price'] is returned as a string
    else:
        logging.error(f"BUY LIMIT order #{order['orderId']} has NOT been filled: {order}")
        return

    # stop-loss
    stop_price = round_step_size(filled_price*stop_loss_multiplier, tick_size)
    logging.info(f"Placing SELL STOP order for {quantity} {pair} at {stop_price}")
    try:
        order = binance.set_stop_loss(pair, quantity, stop_price)
    except Exception as e:
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL STOP order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL STOP #{order['orderId']} has NOT been placed: {order}")

    # take-profit
    stop_price = round_step_size(filled_price*take_profit_multiplier, tick_size)
    logging.info(f"Placing SELL TAKE PROFIT order for {quantity} {pair} at {stop_price}")
    try:
        order = binance.set_take_profit(pair, quantity, stop_price)
    except Exception as e:
        logging.error(e)
        return

    if order['status'] == ORDER_STATUS_NEW:
        logging.info(f"SELL TAKE PROFIT order #{order['orderId']} placed at {order['stopPrice']}")
    else:
        logging.error(f"SELL TAKE PROFIT #{order['orderId']} has NOT been placed: {order}")


class TwitterStream(TwitterStreamAdapter):
    def get_stream(self):
        response = super().get_stream()
        for response_line in response.iter_lines():
            if response_line:
                json_response = json.loads(response_line)
                tweet = json_response['data']

                # if a tweet mentions more than one trading pair this will only pick one (we only have enough $ for one trade anyway)
                pair = json_response['matching_rules'][0]['tag']

                logging.info(f"Tweet {tweet['id']} found for {pair} trading pair")

                thread = threading.Thread(target=launch_trade, args=(pair, ))
                thread.start()
                thread.join()


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

# preloading the config to save time when we're ready to trade
config = load_config(CONFIG_FILE_PATH)
try:
    trade_config = config['trading_pairs']
except KeyError as e:
    logging.error(f"Error loading config: {e}")
    sys.exit()

try:
    aws_secrets = get_aws_secrets(aws_secret_name, AWS_REGION)
except Exception as e:
    logging.error(f"Unable to pull secrets from AWS Secrets Manager: {e}")
    sys.exit()

# unpack the API keys
# TODO catch exceptions here in case a secret is missing in AWS
binance_api_key, binance_api_secret, twitter_api_bearer_token = itemgetter(BINANCE_API_KEY_AWS_SECRET_KEY, BINANCE_API_SECRET_AWS_SECRET_KEY, TWITTER_API_BEARER_TOKEN_AWS_SECRET_KEY)(aws_secrets)

try:
    binance = BinanceFuturesAdapter(
        api_key=binance_api_key,
        api_secret=binance_api_secret,
        test=args.dry_run
    )
except BinanceAPIException as e:
    logging.error(f"Binance API error: {e.message} [{e.status_code}]")
    sys.exit()


def main():
    rules = []
    for symbol, pair_config in trade_config.items():
        # we're pulling the tick size here and adding it to the local config
        # this improves latency by "saving" an API call before placing the orders
        trade_config[symbol]['tick_size'] = binance.get_tick_size(symbol)

        rule = {
            # 'value': '(' + ' OR '.join(pair_config['keywords']) + f') from:{ELON_TWITTER_ID}',
            'value': '(' + ' OR '.join(pair_config['keywords']) + ') -is:retweet',
            'tag': symbol  # we'll use the symbol as a tag, this way we'll know which symbol triggered the trade
        }
        rules.append(rule)

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

    try:
        twitter_stream.get_stream()
    except Exception as e:
        logging.error(e)
        sys.exit()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Program ended")
        sys.exit(0)
