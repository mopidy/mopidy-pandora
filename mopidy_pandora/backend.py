import logging

from mopidy import backend, core

from pandora.errors import PandoraException

import pykka

import requests

from mopidy_pandora import listener, utils

from mopidy_pandora.client import MopidyAPIClient, MopidySettingsDictBuilder
from mopidy_pandora.library import PandoraLibraryProvider
from mopidy_pandora.playback import EventHandlingPlaybackProvider, PandoraPlaybackProvider
from mopidy_pandora.uri import PandoraUri  # noqa: I101


logger = logging.getLogger(__name__)


class PandoraBackend(pykka.ThreadingActor, backend.Backend, core.CoreListener, listener.PandoraFrontendListener,
                     listener.PandoraEventHandlingFrontendListener):

    def __init__(self, config, audio):
        super(PandoraBackend, self).__init__()
        self.config = config['pandora']
        settings = {
            'CACHE_TTL': self.config.get('cache_time_to_live'),
            'API_HOST': self.config.get('api_host'),
            'DECRYPTION_KEY': self.config['partner_decryption_key'],
            'ENCRYPTION_KEY': self.config['partner_encryption_key'],
            'PARTNER_USER': self.config['partner_username'],
            'PARTNER_PASSWORD': self.config['partner_password'],
            'DEVICE': self.config['partner_device'],
            'PROXY': utils.format_proxy(config['proxy']),
            'AUDIO_QUALITY': self.config.get('preferred_audio_quality')
        }

        self.api = MopidySettingsDictBuilder(settings, client_class=MopidyAPIClient).build()
        self.library = PandoraLibraryProvider(backend=self, sort_order=self.config.get('sort_order'))

        self.supports_events = False
        if self.config.get('event_support_enabled'):
            self.supports_events = True
            self.playback = EventHandlingPlaybackProvider(audio, self)
        else:
            self.playback = PandoraPlaybackProvider(audio, self)

        self.uri_schemes = [PandoraUri.SCHEME]

    @utils.run_async
    def on_start(self):
        try:
            self.api.login(self.config['username'], self.config['password'])
            # Prefetch list of stations linked to the user's profile
            self.api.get_station_list()
            # Prefetch genre category list
            self.api.get_genre_stations()
        except requests.exceptions.RequestException:
            logger.exception('Error logging in to Pandora.')

    def end_of_tracklist_reached(self):
        self.prepare_next_track()

    def prepare_next_track(self):
        self._trigger_next_track_available(self.library.get_next_pandora_track())

    def event_triggered(self, track_uri, pandora_event):
        self.process_event(track_uri, pandora_event)

    def process_event(self, track_uri, pandora_event):
        func = getattr(self, pandora_event)
        try:
            logger.info("Triggering event '{}' for Pandora song: '{}'.".format(pandora_event,
                        self.library.lookup_pandora_track(track_uri).song_name))
            func(track_uri)
            self._trigger_event_processed()
        except PandoraException:
            logger.exception('Error calling Pandora event: {}.'.format(pandora_event))
            return False

    def thumbs_up(self, track_uri):
        return self.api.add_feedback(PandoraUri.factory(track_uri).token, True)

    def thumbs_down(self, track_uri):
        return self.api.add_feedback(PandoraUri.factory(track_uri).token, False)

    def sleep(self, track_uri):
        return self.api.sleep_song(PandoraUri.factory(track_uri).token)

    def add_artist_bookmark(self, track_uri):
        return self.api.add_artist_bookmark(PandoraUri.factory(track_uri).token)

    def add_song_bookmark(self, track_uri):
        return self.api.add_song_bookmark(PandoraUri.factory(track_uri).token)

    def _trigger_next_track_available(self, track):
        (listener.PandoraBackendListener.send(listener.PandoraBackendListener.next_track_available.__name__,
                                              track=track))

    def _trigger_event_processed(self):
        listener.PandoraBackendListener.send(listener.PandoraBackendListener.event_processed.__name__)
