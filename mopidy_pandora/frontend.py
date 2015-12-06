import Queue
import threading
from mopidy import core

import pykka

from mopidy_pandora import logger, listener
from mopidy_pandora.uri import TrackUri



class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config
        self.auto_setup = self.config.get('auto_setup', True)

        self.setup_required = True
        self.core = core

    # TODO: only configure when pandora track starts to play
    def on_start(self):
        self.set_options()

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            if self.core.tracklist.get_repeat().get() is True: self.core.tracklist.set_repeat(False)
            if self.core.tracklist.get_consume().get() is False: self.core.tracklist.set_consume(True)
            if self.core.tracklist.get_random().get() is True: self.core.tracklist.set_random(False)
            if self.core.tracklist.get_single().get() is True: self.core.tracklist.set_single(False)

            self.setup_required = False

    def options_changed(self):
        logger.debug('PandoraFrontend: Handling options_changed event')
        self.setup_required = True

    def prepare_change(self):
        logger.debug('PandoraFrontend: Handling prepare_change event')
        if self.is_playing_last_track():
            self._trigger_end_of_tracklist_reached()

        self.set_options()

    def stop(self):
        self.core.playback.stop()

    def is_playing_last_track(self):
        """ Sync the current tracklist information, and add more Pandora tracks to the tracklist as necessary.
        """
        current_tl_track = self.core.playback.get_current_tl_track().get()
        next_tl_track = self.core.tracklist.next_track(current_tl_track).get()

        return next_tl_track is None

    def add_next_pandora_track(self, track):
        logger.debug('PandoraFrontend: Handling add_next_pandora_track event')
        self.core.tracklist.add(uris=[track.uri])

    def _trigger_end_of_tracklist_reached(self):
        logger.debug('PandoraFrontend: Triggering end_of_tracklist_reached event')
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
        self.event_target_uri = None

        self.tracklist_changed_event = threading.Event()
        self.tracklist_changed_event.set()

    def tracklist_changed(self):
        logger.debug('EventSupportPandoraFrontend: Handling tracklist_changed event')

        if self.event_processed_event.isSet():
            self.current_tl_track = self.core.playback.get_current_tl_track().get()
            self.previous_tl_track = self.core.tracklist.previous_track(self.current_tl_track).get()
            self.next_tl_track = self.core.tracklist.next_track(self.current_tl_track).get()
            self.tracklist_changed_event.set()
        else:
            self.tracklist_changed_event.clear()

    # def track_playback_paused(self, tl_track, time_position):
    #     # TODO: REMOVE WORKAROUND.
    #     # Mopidy does not add the track to the history if the user skips to the next track
    #     # while the player is paused (i.e. click pause -> next -> resume). Manually add the track
    #     # to the history until this is fixed.
    #
    #     history = self.core.history.get_history().get()
    #     for tupple in history:
    #         if tupple[1].uri == tl_track.track.uri:
    #             return
    #
    #     self.core.history._add_track(tl_track.track)

    # def track_playback_started(self, tl_track):
    #     logger.debug('EventSupportPandoraFrontend: Handling track_playback_started event')
    #     track_changed = True
    #     self._process_events(tl_track.track.uri, track_changed=track_changed)

    def track_playback_resumed(self, tl_track, time_position):
        logger.debug('EventSupportPandoraFrontend: Handling track_playback_resumed event')
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
            self.event_target_uri = history[1][1].uri
        else:
            # Trigger the event for the track that is playing currently
            self.event_target_uri = track_uri

        if TrackUri.parse(self.event_target_uri).is_ad_uri:
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

        self._trigger_call_event(self.event_target_uri, event)

    def event_processed(self, track_uri):
        logger.debug('EventSupportPandoraFrontend: Handling event_processed event')
        if self.event_target_uri and self.event_target_uri != track_uri:
            logger.error("Unexpected event_processed URI '%s',", track_uri)

        self.event_processed_event.set()
        self.event_target_uri = None
        if not self.tracklist_changed_event.isSet():
            self.tracklist_changed()

    def doubleclicked(self):
        logger.debug('EventSupportPandoraFrontend: Handling doubleclicked event')
        self.event_processed_event.clear()
        self.core.playback.resume()

    def _trigger_call_event(self, track_uri, event):
        logger.debug('EventSupportPandoraFrontend: Triggering call_event event')
        listener.PandoraListener.send('call_event', track_uri=track_uri, pandora_event=event)