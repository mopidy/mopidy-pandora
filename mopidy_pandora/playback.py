from mopidy import backend, models
from mopidy.internal import encoding

from pydora.utils import iterate_forever

import requests

from mopidy_pandora.doubleclick import DoubleClickHandler

from mopidy_pandora.uri import PandoraUri, TrackUri, logger


class PandoraPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self._station = None
        self._station_iter = None
        self.active_track_uri = None

        if self.backend.auto_set_repeat:
            # Make sure that tracks are being played in 'repeat mode'.
            self.audio.set_about_to_finish_callback(self.callback).get()

    def callback(self):
        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

        uri = self.backend.rpc_client.get_current_track_uri()
        if uri is not None and uri.startswith("pandora:"):
            self.backend.rpc_client.set_repeat()

    def change_track(self, track):

        if track.uri is None:
            return False

        station_id = PandoraUri.parse(track.uri).station_id

        if not self._station or station_id != self._station.id:
            self._station = self.backend.api.get_station(station_id)
            self._station_iter = iterate_forever(self._station.get_playlist)

        try:
            next_track = self.get_next_track(TrackUri.parse(track.uri).index)
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
                if consecutive_track_skips >= 4:
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

        self._double_click_handler.on_change_track(self.active_track_uri, track.uri)
        return super(EventSupportPlaybackProvider, self).change_track(track)

    def pause(self):
        self._double_click_handler.set_click()
        return super(EventSupportPlaybackProvider, self).pause()

    def resume(self):
        self._double_click_handler.on_resume_click(self.active_track_uri, self.get_time_position())
        return super(EventSupportPlaybackProvider, self).resume()
