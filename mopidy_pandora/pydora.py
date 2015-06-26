import functools
import logging
from urllib2 import URLError
from mopidy.utils import encoding
import requests
import pandora
from requests.exceptions import ConnectionError

logger = logging.getLogger(__name__)

def authenticated(f):
    @functools.wraps(f)
    def with_authentication(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except pandora.PandoraException as e:
            if e.message == "Invalid Auth Token":
                logger.warning('Pandora session expired, re-authenticating...')
                # Re-authenticate and retry if we lost auth
                self.authenticate()
                return f(self, *args, **kwargs)
            raise
    return with_authentication


class AlwaysOnAPIClient(object):
    """Pydora API Client for Mopidy-Pandora

    This API client automatically re-authenticates itself if the Pandora authorization token
    has expired. This ensures that the Mopidy-Pandora extension will always be available,
    irrespective of how long Mopidy has been running for.

    Detects 'Invalid Auth Token' messages from the Pandora server, and repeats the last
    request after logging in to the Pandora server again.
    """
    def __init__(self, config):
        self.settings = {
            "API_HOST": config.get("api_host", 'tuner.pandora.com/services/json/'),
            "DECRYPTION_KEY": config["partner_decryption_key"],
            "ENCRYPTION_KEY": config["partner_encryption_key"],
            "USERNAME": config["partner_username"],
            "PASSWORD": config["partner_password"],
            "DEVICE": config["partner_device"],
            "DEFAULT_AUDIO_QUALITY": config.get("preferred_audio_quality", 'mediumQuality')
        }
        self.username = config["username"]
        self.password = config["password"]
        self.authenticate()

    def authenticate(self):
        self.api = pandora.APIClient.from_settings_dict(self.settings)
        self.api.login(username=self.username, password=self.password)

    def playable(self, track):
        # Retrieve header information of the track's audio_url. Status code 200 implies that
        # the URL is valid and that the track is accessible
        try:
            r = requests.head(track.audio_url)
            return r.status_code == 200
        except ConnectionError as e:
            error_msg = encoding.locale_decode(e)
            logger.error('Connection error checking if track is playable: %s', error_msg)
            return False

    @authenticated
    def get_station_list(self):
        try:
            return self.api.get_station_list()
        except URLError as e:
            error_msg = encoding.locale_decode(e)
            logger.error('URL error retrieving station list: %s', error_msg)
            return iter(())

    @authenticated
    def get_playlist(self, station_token):

        try:
            return (pandora.models.pandora.PlaylistItem.from_json(self.api, station)
                    for station in self.api.get_playlist(station_token)['items'])
        except URLError as e:
            error_msg = encoding.locale_decode(e)
            logger.error('URL error retrieving playlist: %s', error_msg)
            return iter(())
