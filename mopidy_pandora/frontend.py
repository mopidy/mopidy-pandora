import threading

from mopidy import core

import pykka

from mopidy_pandora import listener, logger
from mopidy_pandora.uri import TrackUri


class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config
        self.auto_setup = self.config.get('auto_setup', True)

        self.setup_required = True
        self.core = core

    def on_start(self):
        self.set_options()

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            assert isinstance(self.core.tracklist, object)
            if self.core.tracklist.get_repeat().get() is True:
                self.core.tracklist.set_repeat(False)
            if self.core.tracklist.get_consume().get() is False:
                self.core.tracklist.set_consume(True)
            if self.core.tracklist.get_random().get() is True:
                self.core.tracklist.set_random(False)
            if self.core.tracklist.get_single().get() is True:
                self.core.tracklist.set_single(False)

            self.setup_required = False

    def options_changed(self):
        self.setup_required = True

    def prepare_change(self):
        if self.is_playing_last_track():
            self._trigger_end_of_tracklist_reached()

        self.set_options()

    def stop(self):
        self.core.playback.stop()

    def is_playing_last_track(self):
        current_tl_track = self.core.playback.get_current_tl_track().get()
        next_tl_track = self.core.tracklist.next_track(current_tl_track).get()

        return next_tl_track is None

    def add_next_pandora_track(self, track):
        self.core.tracklist.add(uris=[track.uri])

    def _trigger_end_of_tracklist_reached(self):
        listener.PandoraListener.send('end_of_tracklist_reached')


class EventSupportPandoraFrontend(PandoraFrontend):

    def __init__(self, config, core):
        super(EventSupportPandoraFrontend, self).__init__(config, core)

        self.on_pause_resume_click = config.get("on_pause_resume_click", "thumbs_up")
        self.on_pause_next_click = config.get("on_pause_next_click", "thumbs_down")
        self.on_pause_previous_click = config.get("on_pause_previous_click", "sleep")

        self.previous_tl_track = None
        self.current_tl_track = None
        self.next_tl_track = None

        self.event_processed_event = threading.Event()
        self.event_processed_event.set()

        self.tracklist_changed_event = threading.Event()
        self.tracklist_changed_event.set()

    def tracklist_changed(self):

        if not self.event_processed_event.isSet():
            # Delay 'tracklist_changed' events until all events have been processed.
            self.tracklist_changed_event.clear()
        else:
            self.current_tl_track = self.core.playback.get_current_tl_track().get()
            self.previous_tl_track = self.core.tracklist.previous_track(self.current_tl_track).get()
            self.next_tl_track = self.core.tracklist.next_track(self.current_tl_track).get()

            self.tracklist_changed_event.set()

    def track_playback_resumed(self, tl_track, time_position):
        track_changed = time_position == 0
        self._process_events(tl_track.track.uri, track_changed=track_changed)

    def _process_events(self, track_uri, track_changed=False):

        # Check if there are any events that still require processing
        if self.event_processed_event.isSet():
            # No events to process
            return

        if track_changed:
            # Trigger the event for the previously played track.
            history = self.core.history.get_history().get()
            event_target_uri = history[1][1].uri
        else:
            # Trigger the event for the track that is playing currently
            event_target_uri = track_uri

        if TrackUri.parse(event_target_uri).is_ad_uri:
            logger.info('Ignoring doubleclick event for advertisement')
            self.event_processed_event.set()
            return

        if track_uri == self.previous_tl_track.track.uri:
            if not track_changed:
                # Resuming playback on the first track in the tracklist.
                event = self.on_pause_resume_click
            else:
                event = self.on_pause_previous_click

        elif track_uri == self.current_tl_track.track.uri:
                event = self.on_pause_resume_click

        elif track_uri == self.next_tl_track.track.uri:
            event = self.on_pause_next_click
        else:
            logger.error("Unexpected doubleclick event URI '%s'", track_uri)
            self.event_processed_event.set()
            return

        self._trigger_call_event(event_target_uri, event)

    def event_processed(self, track_uri):

        self.event_processed_event.set()

        if not self.tracklist_changed_event.isSet():
            # Do any 'tracklist_changed' updates that are pending
            self.tracklist_changed()

    def doubleclicked(self):

        self.event_processed_event.clear()
        # Resume playback of the next track so long...
        self.core.playback.resume()

    def _trigger_call_event(self, track_uri, event):
        listener.PandoraListener.send('call_event', track_uri=track_uri, pandora_event=event)
