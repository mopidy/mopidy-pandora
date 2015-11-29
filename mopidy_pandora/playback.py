import Queue
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

        # TODO: It shouldn't be necessary to keep track of the number of tracks that have been skipped in the
        # player anymore once https://github.com/mopidy/mopidy/issues/1221 has been fixed.
        self.consecutive_track_skips = 0

        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # self.audio.set_about_to_finish_callback(self.callback).get()

        # def callback(self):
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def _auto_setup(self):

        self.backend.rpc_client.set_repeat(False)
        self.backend.rpc_client.set_consume(True)
        self.backend.rpc_client.set_random(False)
        self.backend.rpc_client.set_single(False)

        self.backend.setup_required = False

    def _update_tracklist(self):

        tracklist_length = self.backend.rpc_client.tracklist_get_length()


    def prepare_change(self):

        if self.backend.auto_setup and self.backend.setup_required:
            self._auto_setup()

        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):

        if track.uri is None:
            return False

        pandora_track = self.backend.library.lookup_pandora_track(track.uri)

        try:
            is_playable = pandora_track.audio_url and pandora_track.get_is_playable()
        except requests.exceptions.RequestException as e:
            is_playable = False
            logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))

        if is_playable:
            logger.info("Up next: '%s' by %s", pandora_track.song_name, pandora_track.artist_name)
            self.consecutive_track_skips = 0

            Thread(target=self._update_tracklist).start()

            return super(PandoraPlaybackProvider, self).change_track(track)
        else:
            # TODO: also remove from tracklist? Handled by consume?
            logger.warning("Audio URI for track '%s' cannot be played.", track.uri)
            self._check_skip_limit()
            return False

    def translate_uri(self, uri):
        return self.backend.library.lookup_pandora_track(uri).audio_url

    def _check_skip_limit(self):
        self.consecutive_track_skips += 1

        if self.consecutive_track_skips >= self.SKIP_LIMIT:
            logger.error('Maximum track skip limit (%s) exceeded, stopping...', self.SKIP_LIMIT)
            self.backend.rpc_client.stop_playback()
            return True

        return False


class EventSupportPlaybackProvider(PandoraPlaybackProvider):

    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)
        self._double_click_handler = DoubleClickHandler(backend._config, backend.api)

        self.next_tlid = None
        self.previous_tlid = None

    # def play(self):
    #
    #     Thread(target=self._update_tlids).start()
    #     super(EventSupportPlaybackProvider, self).play()

    def change_track(self, track):

        event_processed = False

        t = self.backend.rpc_client.tracklist_get_previous_tlid()
        try:
            x = t.result_queue.get_nowait()
        except Queue.Empty:
            pass

        if self.next_tlid and self.previous_tlid:
            event_processed = self._double_click_handler.on_change_track(track, self.previous_tlid,
                                                                         self.next_tlid)

        return_value = super(EventSupportPlaybackProvider, self).change_track(track)

        if event_processed:
            self.backend.rpc_client.resume_playback()

        return return_value

    def pause(self):

        if self.get_time_position() > 0:
            self._double_click_handler.set_click_time()

        return super(EventSupportPlaybackProvider, self).pause()

    def resume(self):
        self._double_click_handler.on_resume_click(self.get_time_position())

        return super(EventSupportPlaybackProvider, self).resume()

    # @threaded
    # def _update_tlids(self, a, b):
    #     # self.next_tlid = self.backend.rpc_client.tracklist_get_next_tlid()
    #     # self.previous_tlid = self.backend.rpc_client.tracklist_get_previous_tlid()
    #     a = self.backend.rpc_client.tracklist_get_next_tlid()
    #     b = self.backend.rpc_client.tracklist_get_previous_tlid()
