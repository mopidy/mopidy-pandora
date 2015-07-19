import logging
import pandora

logger = logging.getLogger(__name__)


class MopidyPandoraAPIClient(pandora.APIClient):
    """Pydora API Client for Mopidy-Pandora

    This API client implements caching of the station list.
    """

    def __init__(self, transport, partner_user, partner_password, device,
                 default_audio_quality=pandora.BaseAPIClient.MED_AUDIO_QUALITY):

        super(MopidyPandoraAPIClient, self).__init__(transport, partner_user, partner_password, device,
                                                     default_audio_quality)
        self.station_list = None

    def get_station_list(self):
        if self.station_list is None or not any(self.station_list) or self.station_list.has_changed():
            self.station_list = super(MopidyPandoraAPIClient, self).get_station_list()

        return self.station_list

    def get_station(self, station_token):
        return self.get_station_list()[station_token]

    def get_playlist(self, station_token):
        return super(MopidyPandoraAPIClient, self).get_playlist(station_token)
