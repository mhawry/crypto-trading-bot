import logging
from google.cloud import secretmanager, language_v1
from classes.TwitterStream import TwitterStream
from classes.TextSentiment import TextSentiment
from classes.Telegram import Telegram

GOOGLE_PROJECT_ID = 'winter-berm-302500'  # Google project id for Winter Berm
ELON_TWITTER_ID = 44196397  # Elon Musk's twitter id (will never change)

# secret names from Google Cloud - change them here if they are changed in GCP
TELEGRAM_CHAT_ID_SECRET_KEY = 'telegram-chat-id'
TELEGRAM_TOKEN_SECRET_KEY = 'telegram-token'
TEXT_SENTIMENT_API_KEY_SECRET_KEY = 'text-sentiment-api-key'
TWITTER_BEARER_TOKEN_SECRET_KEY = 'twitter-bearer-token'


def access_google_secret(project_id: str, secret_id: str) -> str:
    """
    Access the payload for the given secret version if one exists. The version
    can be a version number as a string (e.g. "5") or an alias (e.g. "latest").
    """

    # Create the Secret Manager client.
    client = secretmanager.SecretManagerServiceClient()

    # Build the resource name of the secret version.
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    # Access the secret version.
    response = client.access_secret_version(request={'name': name})
    secret = response.payload.data.decode("UTF-8")

    return secret


def test_sentiment():
    # Instantiates a client
    client = language_v1.LanguageServiceClient()

    # The text to analyze
    text = u"dogecoin is going up!!!!"
    document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT)

    # Detects the sentiment of the text
    sentiment = client.analyze_sentiment(request={'document': document}).document_sentiment

    print("Text: {}".format(text))
    print("Sentiment: {}, {}".format(sentiment.score, sentiment.magnitude))


def sample_analyze_entity_sentiment(text_content):
    """
    Analyzing Entity Sentiment in a String

    Args:
      text_content The text content to analyze
    """

    client = language_v1.LanguageServiceClient()

    # Available types: PLAIN_TEXT, HTML
    type_ = language_v1.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
    language = "en"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_entity_sentiment(request = {'document': document, 'encoding_type': encoding_type})
    # Loop through entitites returned from the API
    for entity in response.entities:
        print(u"Representative name for the entity: {}".format(entity.name))
        # Get entity type, e.g. PERSON, LOCATION, ADDRESS, NUMBER, et al
        print(u"Entity type: {}".format(language_v1.Entity.Type(entity.type_).name))
        # Get the salience score associated with the entity in the [0, 1.0] range
        print(u"Salience score: {}".format(entity.salience))
        # Get the aggregate sentiment expressed for this entity in the provided document.
        sentiment = entity.sentiment
        print(u"Entity sentiment score: {}".format(sentiment.score))
        print(u"Entity sentiment magnitude: {}".format(sentiment.magnitude))
        # Loop over the metadata associated with entity. For many known entities,
        # the metadata is a Wikipedia URL (wikipedia_url) and Knowledge Graph MID (mid).
        # Some entity types may have additional metadata, e.g. ADDRESS entities
        # may have metadata for the address street_name, postal_code, et al.
        for metadata_name, metadata_value in entity.metadata.items():
            print(u"{} = {}".format(metadata_name, metadata_value))

        # Loop over the mentions of this entity in the input document.
        # The API currently supports proper noun mentions.
        for mention in entity.mentions:
            print(u"Mention text: {}".format(mention.text.content))
            # Get the mention type, e.g. PROPER for proper noun
            print(
                u"Mention type: {}".format(language_v1.EntityMention.Type(mention.type_).name)
            )

    # Get the language of the text, which will be the same as
    # the language specified in the request or, if not specified,
    # the automatically-detected language.
    print(u"Language of the text: {}".format(response.language))


def basic_text_sentiment_test(tweet):
    text_sentiment_api_key = access_google_secret(GOOGLE_PROJECT_ID, TEXT_SENTIMENT_API_KEY_SECRET_KEY)
    text_sentiment = TextSentiment(text_sentiment_api_key)
    print(text_sentiment.analyse(tweet))


def main():
    sample_analyze_entity_sentiment("bitcoin is the real deal")
    exit()

    logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    # we need a few API keys
    twitter_bearer_token = access_google_secret(GOOGLE_PROJECT_ID, TWITTER_BEARER_TOKEN_SECRET_KEY)
    text_sentiment_api_key = access_google_secret(GOOGLE_PROJECT_ID, TEXT_SENTIMENT_API_KEY_SECRET_KEY)
    telegram_token = access_google_secret(GOOGLE_PROJECT_ID, TELEGRAM_TOKEN_SECRET_KEY)
    telegram_chat_id = access_google_secret(GOOGLE_PROJECT_ID, TELEGRAM_CHAT_ID_SECRET_KEY)

    rules = [
        {"value": f"(Bitcoin OR BTC) from:{ELON_TWITTER_ID} -is:retweet"},
        {"value": "bitcoin", "tag": "test"}  # TODO for testing - remove later
    ]

    twitter_stream = TwitterStream(twitter_bearer_token)
    twitter_stream.set_rules(rules)

    # Start the stream
    tweet_object = twitter_stream.get_stream()

    # If we reach this part it means we have a tweet
    tweet = tweet_object['data']['text']
    text_sentiment = TextSentiment(text_sentiment_api_key)
    sentiment = text_sentiment.analyse(tweet)

    telegram = Telegram(telegram_token)
    telegram.post(telegram_chat_id, f"A {sentiment} tweet has just been posted: {tweet}")


if __name__ == '__main__':
    main()
