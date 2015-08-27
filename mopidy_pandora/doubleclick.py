import logging

import time

from mopidy_pandora.library import PandoraUri

logger = logging.getLogger(__name__)


class DoubleClickHandler(object):
    def __init__(self, config, client):
        self.on_pause_resume_click = config["on_pause_resume_click"]
        self.on_pause_next_click = config["on_pause_next_click"]
        self.on_pause_previous_click = config["on_pause_previous_click"]
        self.double_click_interval = config['double_click_interval']
        self.client = client
        self.click_time = 0

    def set_click(self):
        self.click_time = time.time()

    def is_double_click(self):
        return time.time() - self.click_time < float(self.double_click_interval)

    def on_change_track(self, active_track_uri, new_track_uri):
        from mopidy_pandora.uri import PandoraUri

        if not self.is_double_click():
            return

        # TODO: Won't work if 'shuffle' or 'consume' modes are enabled
        if active_track_uri is not None:

            new_track_index = int(PandoraUri.parse(new_track_uri).index)
            active_track_index = int(PandoraUri.parse(active_track_uri).index)

            if new_track_index > active_track_index or new_track_index == 0 and active_track_index == 2:
                self.process_click(self.on_pause_next_click, active_track_uri)

            elif new_track_index < active_track_index or new_track_index == active_track_index:
                self.process_click(self.on_pause_previous_click, active_track_uri)

    def on_resume_click(self, track_uri, time_position):
        if not self.is_double_click() or time_position == 0:
            return

        self.process_click(self.on_pause_resume_click, track_uri)

    def process_click(self, method, track_uri):
        uri = PandoraUri.parse(track_uri)
        logger.info("Triggering event '%s' for song: %s", method, uri.name)
        func = getattr(self, method)
        func(uri.token)
        self.click_time = 0

    def thumbs_up(self, track_token):
        self.client.add_feedback(track_token, True)

    def thumbs_down(self, track_token):
        self.client.add_feedback(track_token, False)

    def sleep(self, track_token):
        self.client.sleep_song(track_token)

    def add_artist_bookmark(self, track_token):
        self.client.add_artist_bookmark(track_token)

    def add_song_bookmark(self, track_token):
        self.client.add_song_bookmark(track_token)
