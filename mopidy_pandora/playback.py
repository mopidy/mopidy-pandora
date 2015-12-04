import Queue

import threading

import time

from mopidy import backend
from mopidy.internal import encoding

from pandora.errors import PandoraException

import requests

from mopidy_pandora import rpc

from mopidy_pandora.uri import logger, PandoraUri  # noqa I101


class PandoraPlaybackProvider(backend.PlaybackProvider):
    SKIP_LIMIT = 3

    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)

        self.current_tl_track = None
        self.thread_timeout = 2

        # TODO: It shouldn't be necessary to keep track of the number of tracks that have been skipped in the
        # player anymore once https://github.com/mopidy/mopidy/issues/1221 has been fixed.
        self.consecutive_track_skips = 0

        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # self.audio.set_about_to_finish_callback(self.callback).get()

        # def callback(self):
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def _auto_setup(self):

        # Setup player to mirror behaviour of official Pandora front-ends.
        rpc.RPCClient.tracklist_set_repeat(False)
        rpc.RPCClient.tracklist_set_consume(True)
        rpc.RPCClient.tracklist_set_random(False)
        rpc.RPCClient.tracklist_set_single(False)

        self.backend.setup_required = False

    def prepare_change(self):
        if self.backend.auto_setup and self.backend.setup_required:
            self._auto_setup()

        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):

        try:
            if track.uri is None:
                logger.warning("No URI for track '%s': cannot be played.", track.name)
                self._check_skip_limit_exceeded()
                return False

            try:
                pandora_track = self.backend.library.lookup_pandora_track(track.uri)
                is_playable = pandora_track and pandora_track.audio_url and pandora_track.get_is_playable()

            except requests.exceptions.RequestException as e:
                is_playable = False
                logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))

            if is_playable:
                logger.info("Up next: '%s' by %s", pandora_track.song_name, pandora_track.artist_name)
                self.consecutive_track_skips = 0

                return super(PandoraPlaybackProvider, self).change_track(track)
            else:
                logger.warning("Audio URI for track '%s' cannot be played.", track.uri)
                self._check_skip_limit_exceeded()
                return False
        finally:
            # TODO: how to ensure consistent state if tracklist sync fails?
            #       Should we stop playback or retry? Ignore events?
            self._sync_tracklist()

    def translate_uri(self, uri):
        return self.backend.library.lookup_pandora_track(uri).audio_url

    def _check_skip_limit_exceeded(self):
        self.consecutive_track_skips += 1

        if self.consecutive_track_skips >= self.SKIP_LIMIT-1:
            logger.error('Maximum track skip limit (%s) exceeded, stopping...', self.SKIP_LIMIT)
            rpc.RPCClient.playback_stop()
            return True

        return False

    @rpc.run_async
    def _sync_tracklist(self):
        """ Sync the current tracklist information, and add more Pandora tracks to the tracklist as necessary.
        """
        current_tl_track_q = Queue.Queue(1)
        length_q = Queue.Queue(1)
        index_q = Queue.Queue(1)

        try:
            rpc.RPCClient.playback_get_current_tl_track(queue=current_tl_track_q)
            rpc.RPCClient.tracklist_get_length(queue=length_q)

            self.current_tl_track = current_tl_track_q.get(timeout=self.thread_timeout)

            rpc.RPCClient.tracklist_index(tlid=self.current_tl_track['tlid'], queue=index_q)

            tl_index = index_q.get(timeout=self.thread_timeout)
            tl_length = length_q.get(timeout=self.thread_timeout)

            # TODO note that tlid's will be changed to start at '1' instead of '0' in the next release of Mopidy.
            # the following statement should change to 'if index >= length:' when that happens.
            # see https://github.com/mopidy/mopidy/commit/4c5e80a2790c6bea971b105f11ab3f7c16617173
            if tl_index >= tl_length-1:
                # We're at the end of the tracklist, add the next Pandora track
                track = self.backend.library.next_track()

                t = rpc.RPCClient.tracklist_add(uris=[track.uri])
                t.join(self.thread_timeout*2)

        except Exception as e:
            logger.error('Error syncing tracklist: %s.', encoding.locale_decode(e))
            self.current_tl_track = None
            return False

        finally:
            # Cleanup asynchronous queues
            current_tl_track_q.task_done()
            length_q.task_done()
            index_q.task_done()

        return True


class EventSupportPlaybackProvider(PandoraPlaybackProvider):
    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)

        self._doubleclick_processed_event = threading.Event()

        config = self.backend._config
        self.on_pause_resume_click = config["on_pause_resume_click"]
        self.on_pause_next_click = config["on_pause_next_click"]
        self.on_pause_previous_click = config["on_pause_previous_click"]
        self.double_click_interval = config['double_click_interval']

        self._click_time = 0

        self.previous_tl_track = None
        self.next_tl_track = None

    def set_click_time(self, click_time=None):
        if click_time is None:
            self._click_time = time.time()
        else:
            self._click_time = click_time

    def get_click_time(self):
        return self._click_time

    def is_double_click(self):
        double_clicked = self._click_time > 0 and time.time() - self._click_time < float(self.double_click_interval)

        if double_clicked:
            self._doubleclick_processed_event.clear()
        else:
            self._click_time = 0

        return double_clicked

    def change_track(self, track):

        if self.is_double_click():
            if track.uri == self.next_tl_track['track']['uri']:
                self.process_click(self.on_pause_next_click, self.current_tl_track['track']['uri'])

            elif track.uri == self.previous_tl_track['track']['uri']:
                self.process_click(self.on_pause_previous_click, self.current_tl_track['track']['uri'])

            rpc.RPCClient.playback_resume()

        return super(EventSupportPlaybackProvider, self).change_track(track)

    def resume(self):
        if self.is_double_click() and self.get_time_position() > 0:
            self.process_click(self.on_pause_resume_click, self.current_tl_track['track']['uri'])

        return super(EventSupportPlaybackProvider, self).resume()

    def pause(self):
        if self.get_time_position() > 0:
            self.set_click_time()

        return super(EventSupportPlaybackProvider, self).pause()

    @rpc.run_async
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
        finally:
            self._doubleclick_processed_event.set()

    def thumbs_up(self, track_token):
        return self.backend.api.add_feedback(track_token, True)

    def thumbs_down(self, track_token):
        return self.backend.api.add_feedback(track_token, False)

    def sleep(self, track_token):
        return self.backend.api.sleep_song(track_token)

    def add_artist_bookmark(self, track_token):
        return self.backend.api.add_artist_bookmark(track_token)

    def add_song_bookmark(self, track_token):
        return self.backend.api.add_song_bookmark(track_token)

    @rpc.run_async
    def _sync_tracklist(self):
        """ Sync the current tracklist information, to be used when the next
            event needs to be processed.

        """
        previous_tl_track_q = Queue.Queue(1)
        next_tl_track_q = Queue.Queue(1)

        try:

            # Wait until events that depend on the tracklist state have finished processing
            self._doubleclick_processed_event.wait(self.thread_timeout)

            t = super(EventSupportPlaybackProvider, self)._sync_tracklist()
            t.join()

            rpc.RPCClient.tracklist_previous_track(self.current_tl_track, queue=previous_tl_track_q)
            rpc.RPCClient.tracklist_next_track(self.current_tl_track, queue=next_tl_track_q)

            self.previous_tl_track = previous_tl_track_q.get(timeout=self.thread_timeout)
            self.next_tl_track = next_tl_track_q.get(timeout=self.thread_timeout)

        except Exception as e:
            logger.error('Error syncing tracklist: %s.', encoding.locale_decode(e))
            self.previous_tl_track = self.next_tl_track = None
            return False

        finally:
            # Cleanup asynchronous queues
            previous_tl_track_q.task_done()
            next_tl_track_q.task_done()

            # Reset lock so that we are ready to process the next event.
            self._doubleclick_processed_event.set()

        return True
