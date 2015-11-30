import Queue
import copy
from threading import Thread

from mopidy import backend, models
from mopidy.internal import encoding

from pydora.utils import iterate_forever

import requests
from mopidy_pandora import rpc

from mopidy_pandora.doubleclick import DoubleClickHandler

from mopidy_pandora.uri import PandoraUri, TrackUri, logger


class PandoraPlaybackProvider(backend.PlaybackProvider):
    SKIP_LIMIT = 3

    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)

        self.last_played_track_uri = None

        # TODO: It shouldn't be necessary to keep track of the number of tracks that have been skipped in the
        # player anymore once https://github.com/mopidy/mopidy/issues/1221 has been fixed.
        self.consecutive_track_skips = 0

        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # self.audio.set_about_to_finish_callback(self.callback).get()

        # def callback(self):
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def _auto_setup(self):

        rpc.RPCClient.core_tracklist_set_repeat(False)
        rpc.RPCClient.core_tracklist_set_consume(False)
        rpc.RPCClient.core_tracklist_set_random(False)
        rpc.RPCClient.core_tracklist_set_single(False)

        self.backend.setup_required = False

    def _sync_tracklist(self, current_track_uri):

        self.last_played_track_uri = current_track_uri

        length_queue = Queue.Queue()
        rpc.RPCClient.core_tracklist_get_length(queue=length_queue)

        current_tlid_queue = Queue.Queue()
        rpc.RPCClient.core_playback_get_current_tlid(queue=current_tlid_queue)

        current_tlid = current_tlid_queue.get(timeout=2)

        index_queue = Queue.Queue()
        rpc.RPCClient.core_tracklist_index(tlid=current_tlid, queue=index_queue)

        index = index_queue.get(timeout=2)
        length = length_queue.get(timeout=2)

        if index >= length-1:
            # We're at the end of the tracklist, add teh next Pandora track
            track = self.backend.library.next_track()
            rpc.RPCClient.core_tracklist_add(uris=[track.uri])

        length_queue.task_done()
        current_tlid_queue.task_done()
        index_queue.task_done()

    def prepare_change(self):

        if self.backend.auto_setup and self.backend.setup_required:
            self._auto_setup()

        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):

        if track.uri is None:
            return False

        pandora_track = self.backend.library.lookup_pandora_track(track.uri)

        try:
            is_playable = pandora_track and pandora_track.audio_url and pandora_track.get_is_playable()
        except requests.exceptions.RequestException as e:
            is_playable = False
            logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))

        if is_playable:
            logger.info("Up next: '%s' by %s", pandora_track.song_name, pandora_track.artist_name)
            self.consecutive_track_skips = 0

            t = Thread(target=self._sync_tracklist, args=[track.uri])
            t.start()

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
            rpc.RPCClient.core_playback_stop()
            return True

        return False


class EventSupportPlaybackProvider(PandoraPlaybackProvider):

    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)
        self._double_click_handler = DoubleClickHandler(backend)

    def change_track(self, track):

        t = Thread(target=self._double_click_handler.on_change_track, args=[copy.copy(self.last_played_track_uri)])
        t.start()

        return super(EventSupportPlaybackProvider, self).change_track(track)

    def pause(self):

        if self.get_time_position() > 0:
            t = Thread(target=self._double_click_handler.set_click_time)
            t.start()

        return super(EventSupportPlaybackProvider, self).pause()

    def resume(self):

        t = Thread(target=self._double_click_handler.on_resume_click,
                   args=[self.get_time_position(), copy.copy(self.last_played_track_uri)])
        t.start()

        return super(EventSupportPlaybackProvider, self).resume()
