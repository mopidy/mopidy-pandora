from threading import Thread

from mopidy import backend, models
from mopidy.internal import encoding

from pydora.utils import iterate_forever

import requests

from mopidy_pandora.doubleclick import DoubleClickHandler

from mopidy_pandora.uri import PandoraUri, TrackUri, logger


class PandoraPlaybackProvider(backend.PlaybackProvider):
    SKIP_LIMIT = 3

    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self._station = None
        self._station_iter = None
        self.active_track_uri = None

        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # self.audio.set_about_to_finish_callback(self.callback).get()

    # def callback(self):
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def _auto_setup(self):

        self.backend.rpc_client.set_repeat()
        self.backend.rpc_client.set_consume(False)
        self.backend.rpc_client.set_random(False)
        self.backend.rpc_client.set_single(False)

        self.backend.setup_required = False

    def prepare_change(self):

        if self.backend.auto_setup and self.backend.setup_required:
            Thread(target=self._auto_setup).start()

        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):

        if track.uri is None:
            return False

        track_uri = TrackUri.parse(track.uri)

        station_id = PandoraUri.parse(track.uri).station_id

        # TODO: should be able to perform check on is_ad() once dynamic tracklist support is available
        # if not self._station or (not track.is_ad() and station_id != self._station.id):
        if self._station is None or (station_id != '' and station_id != self._station.id):
            self._station = self.backend.api.get_station(station_id)
            self._station_iter = iterate_forever(self._station.get_playlist)

        try:
            next_track = self.get_next_track(track_uri.index)
            if next_track:
                return super(PandoraPlaybackProvider, self).change_track(next_track)
        except requests.exceptions.RequestException as e:
            logger.error('Error changing track: %s', encoding.locale_decode(e))

        return False

    def get_next_track(self, index):
        consecutive_track_skips = 0

        for track in self._station_iter:
            try:
                is_playable = track.audio_url and track.get_is_playable()
            except requests.exceptions.RequestException as e:
                is_playable = False
                logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))

            if is_playable:
                self.active_track_uri = TrackUri.from_track(track, index).uri
                logger.info("Up next: '%s' by %s", track.song_name, track.artist_name)
                return models.Track(uri=self.active_track_uri)
            else:
                consecutive_track_skips += 1
                logger.warning("Track with uri '%s' is not playable.", TrackUri.from_track(track).uri)
                if consecutive_track_skips >= self.SKIP_LIMIT:
                    logger.error('Unplayable track skip limit exceeded!')
                    return None

        return None

    def translate_uri(self, uri):
        return PandoraUri.parse(uri).audio_url


class EventSupportPlaybackProvider(PandoraPlaybackProvider):
    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)
        self._double_click_handler = DoubleClickHandler(backend._config, backend.api)

    def change_track(self, track):

        event_processed = self._double_click_handler.on_change_track(self.active_track_uri, track.uri)
        return_value = super(EventSupportPlaybackProvider, self).change_track(track)

        if event_processed:
            Thread(target=self.backend.rpc_client.resume_playback).start()

        return return_value

    def pause(self):

        if self.get_time_position() > 0:
            self._double_click_handler.set_click_time()

        return super(EventSupportPlaybackProvider, self).pause()

    def resume(self):
        self._double_click_handler.on_resume_click(self.active_track_uri, self.get_time_position())

        return super(EventSupportPlaybackProvider, self).resume()
