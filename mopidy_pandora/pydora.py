from pandora.models.pandora import Station
import requests
from pandora import BaseAPIClient, APIClient, PandoraException

class AlwaysOnAPIClient(APIClient):
    """Pydora API Client for Mopidy-Pandora

    This API client automatically re-authenticates itself if the Pandora authorization token
    has expired. This ensures that the Mopidy-Pandora extension will always be available,
    irrespective of how long Mopidy has been running for.

    Detects 'Invalid Auth Token' messages from the Pandora server, and repeats the last
    request after logging in to the Pandora server again.
    """

    def __init__(self, transport, partner_user, partner_password, device, default_audio_quality=BaseAPIClient.MED_AUDIO_QUALITY):
        super(AlwaysOnAPIClient,self).__init__(transport, partner_user, partner_password, device, default_audio_quality)
        self._stations = []
        self._station_list_checksum = ""

    def login(self, username, password):

        # Store username and password so that client can re-authenticate itself if required.
        self.username = username
        self.password = password

        return super(AlwaysOnAPIClient, self).login(username, password)


    def re_authenticate(self):

        # Invalidate old tokens to ensure that the pydora transport layer creates new ones
        self.transport.user_auth_token = None
        self.transport.partner_auth_token = None

        # Reset sync times for new Pandora session
        self.transport.start_time = None
        self.transport.server_sync_time = None

        self.login(self.username, self.password)


    def playable(self, track):

        # Retrieve header information of the track's audio_url. Status code 200 implies that
        # the URL is valid and that the track is accessible
        url = track.audio_url
        r = requests.head(url)
        if r.status_code == 200:
            return True

        return False

    def _get_station_list(self):
        if not self._stations:
            result = self.transport("user.getStationList", includeStationArtUrl=True)
            self._station_list_checksum = result['checksum']
            self._stations = [Station.from_json(self, s)
                for s in result['stations']]
            return self._stations

        checksum = self.get_station_list_checksum()['checksum']

        if self._station_list_checksum != checksum:
            # Station list has been changed by another Pandora client, invalidate and fetch new list.
            self._stations = []
            self._get_station_list()

        return self._stations


    def get_station_list(self):

        try:
            return self._get_station_list()
        except PandoraException as e:

            if e.message == "Invalid Auth Token":
                self.re_authenticate()
                return self._get_station_list()
            else:
                # Exception is not token related, re-throw to be handled elsewhere
                raise e


    def get_playlist(self, station_token):

        try:
            return super(AlwaysOnAPIClient, self).get_playlist(station_token)
        except PandoraException as e:

            if e.message == "Invalid Auth Token":
                self.re_authenticate()
                return super(AlwaysOnAPIClient, self).get_playlist(station_token)
            else:
                # Exception is not token related, re-throw to be handled elsewhere
                raise e

    def get_station_list_checksum(self):

        return self.transport("user.getStationListChecksum")
