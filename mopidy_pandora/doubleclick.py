import Queue
import logging

import time

from mopidy.internal import encoding

from pandora.errors import PandoraException

from mopidy_pandora import rpc

from mopidy_pandora.library import PandoraUri

logger = logging.getLogger(__name__)


class DoubleClickHandler(object):
    def __init__(self, backend):
        self.backend = backend
        config = self.backend._config
        self.on_pause_resume_click = config["on_pause_resume_click"]
        self.on_pause_next_click = config["on_pause_next_click"]
        self.on_pause_previous_click = config["on_pause_previous_click"]
        self.double_click_interval = config['double_click_interval']
        self.api = self.backend.api
        self._click_time = 0

        self.previous_tlid_queue = Queue.Queue()
        self.next_tlid_queue = Queue.Queue()

    @rpc.run_async
    def set_click_time(self, click_time=None):
        if click_time is None:
            self._click_time = time.time()
        else:
            self._click_time = click_time

        rpc.RPCClient.core_tracklist_get_previous_tlid(queue=self.previous_tlid_queue)
        rpc.RPCClient.core_tracklist_get_next_tlid(queue=self.next_tlid_queue)

    def get_click_time(self):
        return self._click_time

    def is_double_click(self):

        double_clicked = self._click_time > 0 and time.time() - self._click_time < float(self.double_click_interval)

        if double_clicked is False:
            self._click_time = 0

        return double_clicked

    @rpc.run_async
    def on_change_track(self, event_track_uri):

        if not self.is_double_click():
            return False

        # Start playing the next song so long...
        rpc.RPCClient.core_playback_resume()

        try:
            # These tlids should already have been retrieved when 'pause' was clicked to trigger the event
            previous_tlid = self.previous_tlid_queue.get_nowait()
            next_tlid = self.next_tlid_queue.get_nowait()

            # Try to retrieve the current tlid, time out if not found
            current_tlid_queue = Queue.Queue()
            rpc.RPCClient.core_playback_get_current_tlid(queue=current_tlid_queue)
            current_tlid = current_tlid_queue.get(timeout=2)

            # Cleanup asynchronous queues
            current_tlid_queue.task_done()
            self.previous_tlid_queue.task_done()
            self.next_tlid_queue.task_done()

        except Queue.Empty as e:
            logger.error('Error retrieving tracklist IDs: %s. Ignoring event...', encoding.locale_decode(e))
            return False

        if current_tlid == next_tlid:
            return self.process_click(self.on_pause_next_click, event_track_uri)

        elif current_tlid.tlid == previous_tlid:
            return self.process_click(self.on_pause_previous_click, event_track_uri)

        return False

    @rpc.run_async
    def on_resume_click(self, time_position, track_uri):
        if not self.is_double_click() or time_position == 0:
            return False

        return self.process_click(self.on_pause_resume_click, track_uri)

    def process_click(self, method, track_uri):

        self.set_click_time(0)

        uri = PandoraUri.parse(track_uri)
        logger.info("Triggering event '%s' for song: %s", method,
                    self.backend.library.lookup_pandora_track(track_uri).song_name)

        func = getattr(self, method)

        try:
            func(uri.token)
        except PandoraException as e:
            logger.error('Error calling event: %s', encoding.locale_decode(e))
            return False

        return True

    def thumbs_up(self, track_token):
        return self.api.add_feedback(track_token, True)

    def thumbs_down(self, track_token):
        return self.api.add_feedback(track_token, False)

    def sleep(self, track_token):
        return self.api.sleep_song(track_token)

    def add_artist_bookmark(self, track_token):
        return self.api.add_artist_bookmark(track_token)

    def add_song_bookmark(self, track_token):
        return self.api.add_song_bookmark(track_token)
