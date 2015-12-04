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

        # TODO: It shouldn't be necessary to keep track of the number of tracks that have been skipped in the
        # player anymore once https://github.com/mopidy/mopidy/issues/1221 has been fixed.
        self._consecutive_track_skips = 0

        # TODO: add gapless playback when it is supported in Mopidy > 1.1
        # self.audio.set_about_to_finish_callback(self.callback).get()

        # def callback(self):
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    @property
    def consecutive_track_skips(self):
        return self._consecutive_track_skips

    @consecutive_track_skips.setter
    def consecutive_track_skips(self, value=1):
        if value > 0:
            self._consecutive_track_skips += value

            if self.consecutive_track_skips >= self.SKIP_LIMIT-1:
                logger.error('Maximum track skip limit (%s) exceeded, stopping...', self.SKIP_LIMIT)
                self.trigger_stop()
        else:
            self._consecutive_track_skips = 0

    def prepare_change(self):
        if self.backend.auto_setup and self.backend.setup_required:
            self.backend.tracklist.configure()
            self.backend.setup_required = False

        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):
        try:
            if track.uri is None:
                logger.warning("No URI for track '%s'. Track cannot be played.", track.name)
                self.consecutive_track_skips += 1
                return False

            if self.is_playable(track.uri):
                self.consecutive_track_skips = 0
                return super(PandoraPlaybackProvider, self).change_track(track)
            else:
                self.consecutive_track_skips += 1
                return False

        finally:
            # TODO: how to ensure consistent state if tracklist sync fails?
            #       Should we stop playback or retry? Ignore events?
            self.backend.tracklist.sync()

    def translate_uri(self, uri):
        return self.backend.library.lookup_pandora_track(uri).audio_url

    def trigger_resume(self, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.playback.resume', queue=queue)

    def trigger_stop(cls, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.playback.stop', queue=queue)

    def get_current_tl_track(self, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.playback.get_current_tl_track', queue=queue)

    def is_playable(self, track_uri):
        """ A track is playable if it can be retrieved, has a URL, and the Pandora URL can be accessed.

        :param track_uri: uri of the track to be checked.
        :return: True if the track is playable, False otherwise.
        """
        is_playable = False
        try:
            pandora_track = self.backend.library.lookup_pandora_track(track_uri)
            is_playable = pandora_track and pandora_track.audio_url and pandora_track.get_is_playable()

        except requests.exceptions.RequestException as e:
            logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))
        finally:
            return is_playable


class EventSupportPlaybackProvider(PandoraPlaybackProvider):
    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)

        self._doubleclick_processed_event = threading.Event()

        config = self.backend._config
        self.on_pause_resume_click = config.get("on_pause_resume_click", "thumbs_up")
        self.on_pause_next_click = config.get("on_pause_next_click", "thumbs_down")
        self.on_pause_previous_click = config.get("on_pause_previous_click", "sleep")
        self.double_click_interval = float(config.get('double_click_interval', 2.00))

        self._click_time = 0

    def set_click_time(self, click_time=None):
        if click_time is None:
            self._click_time = time.time()
        else:
            self._click_time = click_time

    def get_click_time(self):
        return self._click_time

    def is_double_click(self):
        double_clicked = self._click_time > 0 and time.time() - self._click_time < self.double_click_interval

        if double_clicked:
            self._doubleclick_processed_event.clear()
        else:
            self._click_time = 0

        return double_clicked

    def change_track(self, track):

        if self.is_double_click():
            if track.uri == self.backend.tracklist.next_tl_track['track']['uri']:
                self.process_click(self.on_pause_next_click,
                                   self.backend.tracklist.current_tl_track['track']['uri'])

            elif track.uri == self.backend.tracklist.previous_tl_track['track']['uri']:
                self.process_click(self.on_pause_previous_click,
                                   self.backend.tracklist.current_tl_track['track']['uri'])

            # Resume playback after doubleclick has been processed
            self.trigger_resume()

        # Wait until events that depend on the tracklist state have finished processing
        self._doubleclick_processed_event.wait(rpc.thread_timeout)

        return super(EventSupportPlaybackProvider, self).change_track(track)

    def resume(self):
        if self.is_double_click() and self.get_time_position() > 0:
            self.process_click(self.on_pause_resume_click, self.backend.tracklist.current_tl_track['track']['uri'])

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
            # Reset lock so that we are ready to process the next event.
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
