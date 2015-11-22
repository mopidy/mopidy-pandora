import logging

from mopidy.internal import encoding

import pandora

import requests

logger = logging.getLogger(__name__)


class MopidyPandoraAPIClient(pandora.APIClient):
    """Pydora API Client for Mopidy-Pandora

    This API client implements caching of the station list.
    """

    def __init__(self, transport, partner_user, partner_password, device,
                 default_audio_quality=pandora.BaseAPIClient.MED_AUDIO_QUALITY):

        super(MopidyPandoraAPIClient, self).__init__(transport, partner_user, partner_password, device,
                                                     default_audio_quality)
        self._station_list = []

    def get_station_list(self):

        if not any(self._station_list) or self._station_list.has_changed():
            try:
                self._station_list = super(MopidyPandoraAPIClient, self).get_station_list()
            except requests.exceptions.RequestException as e:
                logger.error('Error retrieving station list: %s', encoding.locale_decode(e))

        return self._station_list

    def get_station(self, station_id):

        try:
            return self.get_station_list()[station_id]
        except TypeError:
            # Could not find station_id in cached list, try retrieving from Pandora server.
            return super(MopidyPandoraAPIClient, self).get_station(station_id)
