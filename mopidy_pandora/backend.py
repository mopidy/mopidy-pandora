from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from mopidy import backend, core

from pandora.errors import PandoraException

import pykka

from mopidy_pandora import listener, utils

from mopidy_pandora.client import MopidyAPIClient, MopidySettingsDictBuilder
from mopidy_pandora.library import PandoraLibraryProvider
from mopidy_pandora.playback import PandoraPlaybackProvider
from mopidy_pandora.uri import PandoraUri  # noqa: I101


logger = logging.getLogger(__name__)


class PandoraBackend(pykka.ThreadingActor, backend.Backend, core.CoreListener, listener.PandoraFrontendListener,
                     listener.EventMonitorListener):

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
        self.playback = PandoraPlaybackProvider(audio, self)
        self.uri_schemes = [PandoraUri.SCHEME]

    def on_start(self):
        self.api.login(self.config['username'], self.config['password'])

    def end_of_tracklist_reached(self, station_id=None, auto_play=False):
        self.prepare_next_track(station_id, auto_play)

    def prepare_next_track(self, station_id, auto_play=False):
        self._trigger_next_track_available(self.library.get_next_pandora_track(station_id), auto_play)

    def event_triggered(self, track_uri, pandora_event):
        self.process_event(track_uri, pandora_event)

    def process_event(self, track_uri, pandora_event):
        func = getattr(self, pandora_event)
        try:
            if pandora_event == 'delete_station':
                logger.info("Triggering event '{}' for Pandora station with ID: '{}'."
                            .format(pandora_event, PandoraUri.factory(track_uri).station_id))
            else:
                logger.info("Triggering event '{}' for Pandora song: '{}'."
                            .format(pandora_event, self.library.lookup_pandora_track(track_uri).song_name))
            func(track_uri)
            self._trigger_event_processed(track_uri, pandora_event)
            return True
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

    def delete_station(self, track_uri):
        r = self.api.delete_station(PandoraUri.factory(track_uri).station_id)
        self.library.refresh()
        self.library.browse(self.library.root_directory.uri)
        return r

    def _trigger_next_track_available(self, track, auto_play=False):
        listener.PandoraBackendListener.send('next_track_available', track=track, auto_play=auto_play)

    def _trigger_event_processed(self, track_uri, pandora_event):
        listener.PandoraBackendListener.send('event_processed', track_uri=track_uri, pandora_event=pandora_event)
