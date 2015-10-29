import logging

import time

from mopidy.internal import encoding

from pandora.errors import PandoraException

from mopidy_pandora.library import PandoraUri

logger = logging.getLogger(__name__)


class DoubleClickHandler(object):
    def __init__(self, config, client):
        self.on_pause_resume_click = config["on_pause_resume_click"]
        self.on_pause_next_click = config["on_pause_next_click"]
        self.on_pause_previous_click = config["on_pause_previous_click"]
        self.double_click_interval = config['double_click_interval']
        self.client = client
        self._click_time = 0

    def set_click_time(self, click_time=None):
        if click_time is None:
            self._click_time = time.time()
        else:
            self._click_time = click_time

    def get_click_time(self):
        return self._click_time

    def is_double_click(self):

        double_clicked = self._click_time > 0 and time.time() - self._click_time < float(self.double_click_interval)

        if double_clicked is False:
            self._click_time = 0

        return double_clicked

    def on_change_track(self, active_track_uri, new_track_uri):
        from mopidy_pandora.uri import PandoraUri

        if not self.is_double_click():
            return False

        if active_track_uri is not None:

            new_track_index = int(PandoraUri.parse(new_track_uri).index)
            active_track_index = int(PandoraUri.parse(active_track_uri).index)

            # TODO: the order of the tracks will no longer be sequential if the user has 'shuffled' the tracklist
            # Need to find a better approach for determining whether 'next' or 'previous' was clicked.
            if new_track_index > active_track_index or new_track_index == 0 and active_track_index == 2:
                return self.process_click(self.on_pause_next_click, active_track_uri)

            elif new_track_index < active_track_index or new_track_index == active_track_index:
                return self.process_click(self.on_pause_previous_click, active_track_uri)

        return False

    def on_resume_click(self, track_uri, time_position):
        if not self.is_double_click() or time_position == 0:
            return False

        return self.process_click(self.on_pause_resume_click, track_uri)

    def process_click(self, method, track_uri):

        self.set_click_time(0)

        uri = PandoraUri.parse(track_uri)
        logger.info("Triggering event '%s' for song: %s", method, uri.name)

        func = getattr(self, method)

        try:
            func(uri.token)
        except PandoraException as e:
            logger.error('Error calling event: %s', encoding.locale_decode(e))
            return False

        return True

    def thumbs_up(self, track_token):
        return self.client.add_feedback(track_token, True)

    def thumbs_down(self, track_token):
        return self.client.add_feedback(track_token, False)

    def sleep(self, track_token):
        return self.client.sleep_song(track_token)

    def add_artist_bookmark(self, track_token):
        return self.client.add_artist_bookmark(track_token)

    def add_song_bookmark(self, track_token):
        return self.client.add_song_bookmark(track_token)
