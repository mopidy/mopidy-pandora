from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time

from cachetools import TTLCache

import pandora
from pandora.clientbuilder import APITransport, DEFAULT_API_HOST, Encryptor, SettingsDictBuilder

import requests


logger = logging.getLogger(__name__)


class MopidySettingsDictBuilder(SettingsDictBuilder):

    def build_from_settings_dict(self, settings):
        enc = Encryptor(settings['DECRYPTION_KEY'],
                        settings['ENCRYPTION_KEY'])

        trans = APITransport(enc,
                             settings.get('API_HOST', DEFAULT_API_HOST),
                             settings.get('PROXY', None))

        quality = settings.get('AUDIO_QUALITY',
                               self.client_class.MED_AUDIO_QUALITY)

        return self.client_class(settings['CACHE_TTL'], trans,
                                 settings['PARTNER_USER'],
                                 settings['PARTNER_PASSWORD'],
                                 settings['DEVICE'], quality)


class MopidyAPIClient(pandora.APIClient):
    """Pydora API Client for Mopidy-Pandora

    This API client implements caching of the station list.
    """

    def __init__(self, cache_ttl, transport, partner_user, partner_password, device,
                 default_audio_quality=pandora.BaseAPIClient.MED_AUDIO_QUALITY):

        super(MopidyAPIClient, self).__init__(transport, partner_user, partner_password, device,
                                              default_audio_quality)

        self.station_list_cache = TTLCache(1, cache_ttl)
        self.genre_stations_cache = TTLCache(1, cache_ttl)

    def get_station_list(self, force_refresh=False):
        station_list = []
        try:
            if (self.station_list_cache.currsize == 0 or
                    (force_refresh and self.station_list_cache.values()[0].has_changed())):

                station_list = super(MopidyAPIClient, self).get_station_list()
                self.station_list_cache[time.time()] = station_list

        except requests.exceptions.RequestException:
            logger.exception('Error retrieving Pandora station list.')
            station_list = []

        try:
            return self.station_list_cache.values()[0]
        except IndexError:
            # Cache disabled
            return station_list

    def get_station(self, station_token):
        try:
            return self.get_station_list()[station_token]
        except TypeError:
            # Could not find station_token in cached list, try retrieving from Pandora server.
            return super(MopidyAPIClient, self).get_station(station_token)

    def get_genre_stations(self, force_refresh=False):
        genre_stations = []
        try:
            if (self.genre_stations_cache.currsize == 0 or
                    (force_refresh and self.genre_stations_cache.values()[0].has_changed())):

                genre_stations = super(MopidyAPIClient, self).get_genre_stations()
                self.genre_stations_cache[time.time()] = genre_stations

        except requests.exceptions.RequestException:
            logger.exception('Error retrieving Pandora genre stations.')
            return genre_stations

        try:
            return self.genre_stations_cache.values()[0]
        except IndexError:
            # Cache disabled
            return genre_stations
