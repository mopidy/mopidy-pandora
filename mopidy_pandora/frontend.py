import logging
import threading

from mopidy import core
from mopidy.audio import PlaybackState

import pykka

from mopidy_pandora import listener
from mopidy_pandora.uri import AdItemUri, PandoraUri


logger = logging.getLogger(__name__)


def only_execute_for_pandora_uris(func):
    """ Function decorator intended to ensure that "func" is only executed if a Pandora track
        is currently playing. Allows CoreListener events to be ignored if they are being raised
        while playing non-Pandora tracks.

    :param func: the function to be executed
    :return: the return value of the function if it was run, or 'None' otherwise.
    """
    from functools import wraps

    @wraps(func)
    def check_pandora(self, *args, **kwargs):
        """ Check if a pandora track is currently being played.

        :param args: all arguments will be passed to the target function
        :param kwargs: active_uri should contain the uri to be checked, all other kwargs
               will be passed to the target function
        :return: the return value of the function if it was run or 'None' otherwise.
        """
        try:
            PandoraUri.factory(self.core.playback.get_current_tl_track().get().track.uri)
            return func(self, *args, **kwargs)
        except (AttributeError, NotImplementedError):
            # Not playing a Pandora track. Don't do anything.
            pass

    return check_pandora


class PandoraFrontendFactory(pykka.ThreadingActor):

    def __new__(cls, config, core):
        if config['pandora'].get('event_support_enabled'):
            return EventHandlingPandoraFrontend(config, core)
        else:
            return PandoraFrontend(config, core)


class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraBackendListener,
                      listener.PandoraPlaybackListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config['pandora']
        self.auto_setup = self.config.get('auto_setup')

        self.setup_required = True
        self.core = core

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            assert isinstance(self.core.tracklist, object)
            if self.core.tracklist.get_repeat().get() is False:
                self.core.tracklist.set_repeat(True)
            if self.core.tracklist.get_consume().get() is True:
                self.core.tracklist.set_consume(False)
            if self.core.tracklist.get_random().get() is True:
                self.core.tracklist.set_random(False)
            if self.core.tracklist.get_single().get() is True:
                self.core.tracklist.set_single(False)

            self.setup_required = False

    def options_changed(self):
        self.setup_required = True

    @only_execute_for_pandora_uris
    def track_playback_started(self, tl_track):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_ended(self, tl_track, time_position):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_paused(self, tl_track, time_position):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        self.set_options()

    def track_changed(self, track):
        if self.core.tracklist.index().get() == self.core.tracklist.get_length().get() - 1:
            self._trigger_end_of_tracklist_reached()

    def next_track_available(self, track):
        self.add_track(track)

    def skip_limit_exceeded(self):
        self.core.playback.stop()

    def add_track(self, track):
        # Add the next Pandora track
        self.core.tracklist.add(uris=[track.uri]).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        if self.core.playback.get_state().get() == PlaybackState.STOPPED:
            # Playback stopped after previous track was unplayable. Resume playback with the freshly seeded tracklist.
            self.core.playback.play(tl_tracks[-1]).get()
        if len(tl_tracks) > 2:
            # Only need two tracks in the tracklist at any given time, remove the oldest tracks
            self.core.tracklist.remove({'tlid': [tl_tracks[t].tlid for t in range(0, len(tl_tracks)-2)]}).get()

    def _trigger_end_of_tracklist_reached(self):
        listener.PandoraFrontendListener.send(listener.PandoraFrontendListener.end_of_tracklist_reached.__name__)


class EventHandlingPandoraFrontend(PandoraFrontend, listener.PandoraEventHandlingPlaybackListener):

    def __init__(self, config, core):
        super(EventHandlingPandoraFrontend, self).__init__(config, core)

        self.settings = {
            'OPR_EVENT': config['pandora'].get('on_pause_resume_click'),
            'OPN_EVENT': config['pandora'].get('on_pause_next_click'),
            'OPP_EVENT': config['pandora'].get('on_pause_previous_click')
        }

        self.last_played_track_uri = None
        self.upcoming_track_uri = None

        self.event_processed_event = threading.Event()
        self.event_processed_event.set()

        self.tracklist_changed_event = threading.Event()
        self.tracklist_changed_event.set()

    @only_execute_for_pandora_uris
    def tracklist_changed(self):

        if self.event_processed_event.isSet():
            # Keep track of current and next tracks so that we can determine direction of future track changes.
            current_tl_track = self.core.playback.get_current_tl_track().get()
            self.last_played_track_uri = current_tl_track.track.uri
            self.upcoming_track_uri = self.core.tracklist.next_track(current_tl_track).get().track.uri

            self.tracklist_changed_event.set()
        else:
            # Delay 'tracklist_changed' events until all events have been processed.
            self.tracklist_changed_event.clear()

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        super(EventHandlingPandoraFrontend, self).track_playback_resumed(tl_track, time_position)

        self._process_events(tl_track.track.uri, time_position)

    def _process_events(self, track_uri, time_position):

        # Check if there are any events that still require processing.
        if self.event_processed_event.isSet():
            # No events to process.
            return

        event_target_uri = self._get_event_target_uri(track_uri, time_position)
        assert event_target_uri

        if type(PandoraUri.factory(event_target_uri)) is AdItemUri:
            logger.info('Ignoring doubleclick event for advertisement')
            self.event_processed_event.set()
            return

        try:
            self._trigger_event_triggered(event_target_uri, self._get_event(track_uri, time_position))
        except ValueError:
            logger.exception("Error processing Pandora event for URI '{}'. Ignoring event...".format(event_target_uri))
            self.event_processed_event.set()
            return

    def _get_event_target_uri(self, track_uri, time_position):
        if time_position == 0:
            # Track was just changed, trigger the event for the previously played track.
            history = self.core.history.get_history().get()
            return history[1][1].uri
        else:
            # Trigger the event for the track that is playing currently.
            return track_uri

    def _get_event(self, track_uri, time_position):
        if track_uri == self.last_played_track_uri:
            if time_position > 0:
                # Resuming playback on the first track in the tracklist.
                return self.settings['OPR_EVENT']
            else:
                return self.settings['OPP_EVENT']

        elif track_uri == self.upcoming_track_uri:
            return self.settings['OPN_EVENT']
        else:
            raise ValueError('Unexpected event URI: {}'.format(track_uri))

    def event_processed(self):
        self.event_processed_event.set()

        if not self.tracklist_changed_event.isSet():
            # Do any 'tracklist_changed' updates that are pending.
            self.tracklist_changed()

    def doubleclicked(self):
        self.event_processed_event.clear()
        # Resume playback...
        if self.core.playback.get_state().get() != PlaybackState.PLAYING:
            self.core.playback.resume().get()

    def _trigger_event_triggered(self, track_uri, event):
        (listener.PandoraFrontendListener.send(listener.PandoraEventHandlingFrontendListener.event_triggered.__name__,
                                               track_uri=track_uri, pandora_event=event))
