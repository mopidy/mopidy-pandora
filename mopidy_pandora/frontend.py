from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import threading

import time

from collections import namedtuple

from mopidy import core
from mopidy.audio import PlaybackState

import pykka

from mopidy_pandora import listener
from mopidy_pandora.uri import AdItemUri, PandoraUri
from mopidy_pandora.utils import run_async

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
        self.set_options()

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

    def is_end_of_tracklist_reached(self, track=None):
        length = self.core.tracklist.get_length().get()
        if length <= 1:
            return True
        if track:
            tl_track = self.core.tracklist.filter({'uri': [track.uri]}).get()[0]
            track_index = self.core.tracklist.index(tl_track).get()
        else:
            track_index = self.core.tracklist.index().get()

        return track_index == length - 1

    def is_station_changed(self, track):
        try:
            previous_track_uri = PandoraUri.factory(self.core.history.get_history().get()[1][1].uri)
            if previous_track_uri.station_id != PandoraUri.factory(track.uri).station_id:
                return True
        except (IndexError, NotImplementedError):
            # No tracks in history, or last played track was not a Pandora track. Ignore
            pass
        return False

    def changing_track(self, track):
        if self.is_station_changed(track):
            # Station has changed, remove tracks from previous station from tracklist.
            self._trim_tracklist(keep_only=track)
        if self.is_end_of_tracklist_reached(track):
            self._trigger_end_of_tracklist_reached(PandoraUri.factory(track).station_id,
                                                   auto_play=False)

    def track_unplayable(self, track):
        if self.is_end_of_tracklist_reached(track):
            self.core.playback.stop()
            self._trigger_end_of_tracklist_reached(PandoraUri.factory(track).station_id,
                                                   auto_play=True)

        self.core.tracklist.remove({'uri': [track.uri]}).get()

    def next_track_available(self, track, auto_play=False):
        if track:
            self.add_track(track, auto_play)
        else:
            logger.warning('No more Pandora tracks available to play.')
            self.core.playback.stop()

    def skip_limit_exceeded(self):
        self.core.playback.stop()

    def add_track(self, track, auto_play=False):
        # Add the next Pandora track
        self.core.tracklist.add(uris=[track.uri]).get()
        if auto_play:
            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            self.core.playback.play(tlid=tl_tracks[-1].tlid).get()
        self._trim_tracklist(maxsize=2)

    def _trim_tracklist(self, keep_only=None, maxsize=2):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        if keep_only:
            trim_tlids = [t.tlid for t in tl_tracks if t.track.uri != keep_only.uri]
            if len(trim_tlids) > 0:
                return len(self.core.tracklist.remove({'tlid': trim_tlids}).get())
            else:
                return 0

        elif len(tl_tracks) > maxsize:
            # Only need two tracks in the tracklist at any given time, remove the oldest tracks
            return len(self.core.tracklist.remove(
                {'tlid': [tl_tracks[t].tlid for t in range(0, len(tl_tracks)-maxsize)]}
            ).get())

    def _trigger_end_of_tracklist_reached(self, station_id, auto_play=False):
        listener.PandoraFrontendListener.send('end_of_tracklist_reached', station_id=station_id, auto_play=auto_play)


ClickMarker = namedtuple('ClickMarker', 'uri, time')


class EventHandlingPandoraFrontend(PandoraFrontend):

    def __init__(self, config, core):
        super(EventHandlingPandoraFrontend, self).__init__(config, core)

        self.settings = {
            'resume': config['pandora'].get('on_pause_resume_click'),
            'change_track_next': config['pandora'].get('on_pause_next_click'),
            'change_track_previous': config['pandora'].get('on_pause_previous_click'),
            'stop': config['pandora'].get('on_pause_stop_click')
        }

        self.double_click_interval = float(config['pandora'].get('double_click_interval'))
        self._click_marker = None

        self.change_track_event = threading.Event()
        self.change_track_event.set()

    @only_execute_for_pandora_uris
    def track_playback_paused(self, tl_track, time_position):
        """
        Clicking 'pause' is always the first step in detecting a double click. It also sets the timer that will be used
        to check for double clicks later on.

        """
        if time_position > 0:
            self.set_click_marker(tl_track)
        super(EventHandlingPandoraFrontend, self).track_playback_paused(tl_track, time_position)

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        """
        Used to detect pause -> resume double click events.

        """
        if self._is_double_click():
            self._queue_event(event='resume')
        super(EventHandlingPandoraFrontend, self).track_playback_resumed(tl_track, time_position)

    @only_execute_for_pandora_uris
    def playback_state_changed(self, old_state, new_state):
        """
        Used to detect pause -> stop, pause -> previous, and pause -> next double click events.

        """
        if old_state == PlaybackState.PAUSED and new_state == PlaybackState.STOPPED:
            if self._is_double_click():
                # Mopidy (as of 1.1.2) always forces a call to core.playback.stop() when the track changes, even
                # if the user did not click stop explicitly. We need to wait for a 'change_track' event
                # immediately thereafter to know if this is a real track stop, or just a transition to the
                # next/previous track.
                self._queue_event('stop', self.change_track_event, 'change_track', timeout=self.double_click_interval)
        super(EventHandlingPandoraFrontend, self).playback_state_changed(old_state, new_state)

    def changing_track(self, track):
        self.change_track_event.set()
        super(EventHandlingPandoraFrontend, self).changing_track(track)

    def set_click_marker(self, tl_track, click_time=None):
        if click_time is None:
            click_time = int(time.time() * 1000)

        self._click_marker = ClickMarker(tl_track.track.uri, click_time)

    def get_click_marker(self):
        return self._click_marker

    def event_processed(self, track_uri, pandora_event):
        if pandora_event == 'delete_station':
            self.core.tracklist.clear()

    def _is_double_click(self):
        if self._click_marker is None:
            return False
        return (self._click_marker.time > 0 and
                int(time.time() * 1000) - self._click_marker.time < self.double_click_interval * 1000)

    @run_async
    def _queue_event(self, event, threading_event=None, override_event=None, timeout=None):
        """
        Queue an event for processing. If the specified threading event is set, then the event will be overridden with
        the one specified. Useful for detecting track change transitions, which always trigger 'stop' first.

        :param event: the original event action that was originally called.
        :param threading_event: the threading.Event to monitor.
        :param override_event:  the new event that should be called instead of the original if the threading event is
                                set within the timeout specified.
        :param timeout: the length of time to wait for the threading.Event to be set before processing the orignal event
        """

        if threading_event:
            threading_event.clear()
            if threading_event.wait(timeout=timeout):
                event = override_event

        self.process_event(event=event)

    def process_event(self, event):
        try:
            event_target_uri, event_target_action = self._get_event_targets(action=event)
        except KeyError:
            logger.exception("Error processing Pandora event '{}', ignoring...".format(event))
            return
        else:
            if type(PandoraUri.factory(event_target_uri)) is AdItemUri:
                logger.info('Ignoring doubleclick event for Pandora advertisement...')
                return

            self._trigger_event_triggered(event_target_uri, event_target_action)
            # Resume playback...
            if event == 'change_track' and self.core.playback.get_state().get() != PlaybackState.PLAYING:
                self.core.playback.resume().get()

    def _get_event_targets(self, action=None):
        if action == 'change_track':
            history = self.core.history.get_history().get()
            for i, h in enumerate(history):
                if h[0] < self._click_marker.time:
                    if h[1].uri == self._click_marker.uri:
                        # This is the point in time in the history that the track was played
                        # before the double_click event occurred.
                        if history[i-1][1].uri == self._click_marker.uri:
                            # Track was played again immediately after double_click.
                            # User clicked 'previous' in consume mode.
                            action = 'change_track_previous'
                            break
                        else:
                            # Switched to another track, user clicked 'next'.
                            action = 'change_track_next'
                            break

        return self._click_marker.uri, self.settings[action]

    def _trigger_event_triggered(self, track_uri, event):
        self._click_marker = None
        (listener.PandoraEventHandlingFrontendListener.send('event_triggered',
                                                            track_uri=track_uri,
                                                            pandora_event=event))
