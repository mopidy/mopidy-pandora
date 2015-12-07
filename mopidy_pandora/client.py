import logging

from cachetools import TTLCache

from mopidy.internal import encoding

import pandora
from pandora.clientbuilder import APITransport, DEFAULT_API_HOST, Encryptor, SettingsDictBuilder

import requests

logger = logging.getLogger(__name__)


class MopidySettingsDictBuilder(SettingsDictBuilder):

    def build_from_settings_dict(self, settings):
        enc = Encryptor(settings["DECRYPTION_KEY"],
                        settings["ENCRYPTION_KEY"])

        trans = APITransport(enc,
                             settings.get("API_HOST", DEFAULT_API_HOST),
                             settings.get("PROXY", None))

        quality = settings.get("AUDIO_QUALITY",
                               self.client_class.MED_AUDIO_QUALITY)

        return self.client_class(settings["CACHE_TTL"], trans,
                                 settings["PARTNER_USER"],
                                 settings["PARTNER_PASSWORD"],
                                 settings["DEVICE"], quality)


class MopidyAPIClient(pandora.APIClient):
    """Pydora API Client for Mopidy-Pandora

    This API client implements caching of the station list.
    """

    station_key = "stations"
    genre_key = "genre_stations"

    def __init__(self, cache_ttl, transport, partner_user, partner_password, device,
                 default_audio_quality=pandora.BaseAPIClient.MED_AUDIO_QUALITY):

        super(MopidyAPIClient, self).__init__(transport, partner_user, partner_password, device,
                                              default_audio_quality)

        self._pandora_api_cache = TTLCache(1, cache_ttl)

    def get_station_list(self, force_refresh=False):

        try:
            if MopidyAPIClient.station_key not in self._pandora_api_cache.keys() or \
                    (force_refresh and self._pandora_api_cache[MopidyAPIClient.station_key].has_changed()):

                self._pandora_api_cache[MopidyAPIClient.station_key] = \
                    super(MopidyAPIClient, self).get_station_list()

        except requests.exceptions.RequestException as e:
            logger.error('Error retrieving station list: %s', encoding.locale_decode(e))
            return []

        return self._pandora_api_cache[MopidyAPIClient.station_key]

    def get_station(self, station_id):

        try:
            return self.get_station_list()[station_id]
        except TypeError:
            # Could not find station_id in cached list, try retrieving from Pandora server.
            return super(MopidyAPIClient, self).get_station(station_id)

    def get_genre_stations(self, force_refresh=False):

        try:
            if MopidyAPIClient.genre_key not in self._pandora_api_cache.keys() or \
                    (force_refresh and self._pandora_api_cache[MopidyAPIClient.genre_key].has_changed()):

                self._pandora_api_cache[MopidyAPIClient.genre_key] = \
                    super(MopidyAPIClient, self).get_genre_stations()

        except requests.exceptions.RequestException as e:
            logger.error('Error retrieving genre stations: %s', encoding.locale_decode(e))
            return []

        return self._pandora_api_cache[MopidyAPIClient.genre_key]
