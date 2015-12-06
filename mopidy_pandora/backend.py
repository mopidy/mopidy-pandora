from mopidy import backend, core
from mopidy.internal import encoding

from pandora import BaseAPIClient
from pandora.errors import PandoraException

import pykka

import requests

from mopidy_pandora import listener, rpc


from mopidy_pandora.client import MopidyPandoraAPIClient, MopidyPandoraSettingsDictBuilder
from mopidy_pandora.library import PandoraLibraryProvider
from mopidy_pandora.playback import EventSupportPlaybackProvider, PandoraPlaybackProvider
from mopidy_pandora.uri import logger, PandoraUri  # noqa: I101


class PandoraBackend(pykka.ThreadingActor, backend.Backend, core.CoreListener, listener.PandoraListener):

    def __init__(self, config, audio):
        super(PandoraBackend, self).__init__()
        self.config = config['pandora']
        settings = {
            "CACHE_TTL": self.config.get("cache_time_to_live", 1800),
            "API_HOST": self.config.get("api_host", 'tuner.pandora.com/services/json/'),
            "DECRYPTION_KEY": self.config["partner_decryption_key"],
            "ENCRYPTION_KEY": self.config["partner_encryption_key"],
            "PARTNER_USER": self.config["partner_username"],
            "PARTNER_PASSWORD": self.config["partner_password"],
            "DEVICE": self.config["partner_device"],
            "AUDIO_QUALITY": self.config.get("preferred_audio_quality", BaseAPIClient.HIGH_AUDIO_QUALITY)
        }

        self.api = MopidyPandoraSettingsDictBuilder(settings, client_class=MopidyPandoraAPIClient).build()
        self.library = PandoraLibraryProvider(backend=self, sort_order=self.config.get('sort_order', 'date'))

        self.supports_events = False
        if self.config.get('event_support_enabled', True):
            self.supports_events = True
            self.playback = EventSupportPlaybackProvider(audio=audio, backend=self)
        else:
            self.playback = PandoraPlaybackProvider(audio=audio, backend=self)

        self.uri_schemes = ['pandora']

    @rpc.run_async
    def on_start(self):
        try:
            self.api.login(self.config["username"], self.config["password"])
            # Prefetch list of stations linked to the user's profile
            self.api.get_station_list()
            # Prefetch genre category list
            self.api.get_genre_stations()
        except requests.exceptions.RequestException as e:
            logger.error('Error logging in to Pandora: %s', encoding.locale_decode(e))

    def end_of_tracklist_reached(self):
        next_track = self.library.next_track()
        if next_track:
            self._trigger_add_next_pandora_track(next_track)

    def _trigger_add_next_pandora_track(self, track):
        listener.PandoraListener.send('add_next_pandora_track', track=track)

    def _trigger_event_processed(self, track_uri):
        listener.PandoraListener.send('event_processed', track_uri=track_uri)

    def call_event(self, track_uri, pandora_event):
        func = getattr(self, pandora_event)
        try:
            logger.info("Triggering event '%s' for song: %s", pandora_event,
                        self.library.lookup_pandora_track(track_uri).song_name)
            func(track_uri)
            self._trigger_event_processed(track_uri)
        except PandoraException as e:
            logger.error('Error calling event: %s', encoding.locale_decode(e))
            return False

    def thumbs_up(self, track_uri):
        return self.api.add_feedback(PandoraUri.parse(track_uri).token, True)

    def thumbs_down(self, track_uri):
        return self.api.add_feedback(PandoraUri.parse(track_uri).token, False)

    def sleep(self, track_uri):
        return self.api.sleep_song(PandoraUri.parse(track_uri).token)

    def add_artist_bookmark(self, track_uri):
        return self.api.add_artist_bookmark(PandoraUri.parse(track_uri).token)

    def add_song_bookmark(self, track_uri):
        return self.api.add_song_bookmark(PandoraUri.parse(track_uri).token)
