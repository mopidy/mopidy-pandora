import time

from mopidy import backend
from mopidy.internal import encoding

import requests

from mopidy_pandora import listener

from mopidy_pandora.uri import logger


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

    def change_pandora_track(self, track):
        """ Attempt to retrieve and check the Pandora playlist item from the buffer.

        A track is playable if it has been stored in the buffer, has a URL, and the Pandora URL can be accessed.

        :param track: the track to retrieve and check the Pandora playlist item for.
        :return: True if the track is playable, False otherwise.
        """
        try:
            pandora_track = self.backend.library.lookup_pandora_track(track.uri)
            if not (pandora_track and pandora_track.audio_url and pandora_track.get_is_playable()):
                # Track is not playable.
                self._consecutive_track_skips += 1

                if self._consecutive_track_skips >= self.SKIP_LIMIT:
                    raise MaxSkipLimitExceeded(('Maximum track skip limit ({:d}) exceeded, stopping...'
                                                .format(self.SKIP_LIMIT)))

                # Prepare the next track to be checked on the next call of 'change_track'.
                self.backend.prepare_next_track(True)
                raise Unplayable('Track with URI \'{}\' is not playable'.format(track.uri))

        except requests.exceptions.RequestException as e:
            raise Unplayable('Error checking if track is playable: {}'.format(encoding.locale_decode(e)))

        # Success, reset track skip counter.
        self._consecutive_track_skips = 0
        return super(PandoraPlaybackProvider, self).change_track(track)

    def prepare_change(self):
        self.backend.prepare_next_track(False)
        super(PandoraPlaybackProvider, self).prepare_change()

    def change_track(self, track):
        if track.uri is None:
            logger.warning('No URI for track \'{}\'. Track cannot be played.'.format(track))
            return False

        try:
            return self.change_pandora_track(track)
        except KeyError:
            logger.error('Error changing track: failed to lookup \'{}\''.format(track.uri))
            return False
        except (MaxSkipLimitExceeded, Unplayable) as e:
            logger.error('Error changing track: ({})'.format(encoding.locale_decode(e)))
            return False

    def translate_uri(self, uri):
        return self.backend.library.lookup_pandora_track(uri).audio_url


class EventSupportPlaybackProvider(PandoraPlaybackProvider):
    def __init__(self, audio, backend):
        super(EventSupportPlaybackProvider, self).__init__(audio, backend)

        self.double_click_interval = float(backend.config.get('double_click_interval', 2.00))
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

        if not double_clicked:
            self.set_click_time(0)

        return double_clicked

    def change_track(self, track):

        if self.is_double_click():
            self._trigger_doubleclicked()
            self.set_click_time(0)

        return super(EventSupportPlaybackProvider, self).change_track(track)

    def resume(self):
        if self.is_double_click() and self.get_time_position() > 0:
            self._trigger_doubleclicked()

        return super(EventSupportPlaybackProvider, self).resume()

    def pause(self):
        if self.get_time_position() > 0:
            self.set_click_time()

        return super(EventSupportPlaybackProvider, self).pause()

    def _trigger_doubleclicked(self):
        listener.PandoraListener.send('doubleclicked')


class MaxSkipLimitExceeded(Exception):
    pass


class Unplayable(Exception):
    pass
