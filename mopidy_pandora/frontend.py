from __future__ import absolute_import, division, print_function, unicode_literals

import Queue

import logging

import threading

import time

from collections import namedtuple
from difflib import SequenceMatcher
from functools import total_ordering

from mopidy import audio, core
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

        :param args: all arguments will be passed to the target function.
        :param kwargs: all kwargs will be passed to the target function.
        :return: the return value of the function if it was run or 'None' otherwise.
        """
        uri = get_active_uri(self.core, *args, **kwargs)
        if uri and PandoraUri.is_pandora_uri(uri):
            return func(self, *args, **kwargs)

    return check_pandora


def get_active_uri(core, *args, **kwargs):
    """
    Tries to determine what the currently 'active' Mopidy track is, and returns it's URI. Makes use of a best-effort
    determination base on:
    1. looking for 'track' in kwargs, then
    2. 'tl_track' in kwargs, then
    3. interrogating the Mopidy core for the currently playing track, and lastly
    4. checking which track was played last according to the history that Mopidy keeps.

    :param core: the Mopidy core that can be used as a fallback if no suitable arguments are available.
    :param args: all available arguments from the calling function.
    :param kwargs: all available kwargs from the calling function.
    :return: the URI of the active Mopidy track, if it could be determined, or None otherwise.
    """
    uri = None
    track = kwargs.get('track', None)
    if track:
        uri = track.uri
    else:
        tl_track = kwargs.get('tl_track', core.playback.get_current_tl_track().get())
        if tl_track:
            uri = tl_track.track.uri
    if not uri:
        history = core.history.get_history().get()
        if history:
            uri = history[0]
    return uri


class PandoraFrontend(pykka.ThreadingActor,
                      core.CoreListener,
                      listener.PandoraBackendListener,
                      listener.PandoraPlaybackListener,
                      listener.EventMonitorListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config['pandora']
        self.auto_setup = self.config.get('auto_setup')

        self.setup_required = True
        self.core = core

        self.track_change_completed_event = threading.Event()
        self.track_change_completed_event.set()

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            if self.core.tracklist.get_consume().get() is False:
                self.core.tracklist.set_consume(True)
                return
            if self.core.tracklist.get_repeat().get() is True:
                self.core.tracklist.set_repeat(False)
                return
            if self.core.tracklist.get_random().get() is True:
                self.core.tracklist.set_random(False)
                return
            if self.core.tracklist.get_single().get() is True:
                self.core.tracklist.set_single(False)
                return

            self.setup_required = False

    @only_execute_for_pandora_uris
    def options_changed(self):
        self.setup_required = True
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_started(self, tl_track):
        self.set_options()
        if not self.track_change_completed_event.is_set():
            self.track_change_completed_event.set()
            self.update_tracklist(tl_track.track)

    @only_execute_for_pandora_uris
    def track_playback_ended(self, tl_track, time_position):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_paused(self, tl_track, time_position):
        self.set_options()
        if not self.track_change_completed_event.is_set():
            self.track_change_completed_event.set()
            self.update_tracklist(tl_track.track)

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

    def track_changing(self, track):
        self.track_change_completed_event.clear()

    def update_tracklist(self, track):
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

        self.core.tracklist.remove({'uri': [track.uri]})

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
        self.core.tracklist.add(uris=[track.uri])
        if auto_play:
            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            self.core.playback.play(tlid=tl_tracks[-1].tlid)
        self._trim_tracklist(maxsize=2)

    def _trim_tracklist(self, keep_only=None, maxsize=2):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        if keep_only:
            trim_tlids = [t.tlid for t in tl_tracks if t.track.uri != keep_only.uri]
            if len(trim_tlids) > 0:
                return self.core.tracklist.remove({'tlid': trim_tlids})
            else:
                return 0

        elif len(tl_tracks) > maxsize:
            # Only need two tracks in the tracklist at any given time, remove the oldest tracks
            return self.core.tracklist.remove(
                {'tlid': [tl_tracks[t].tlid for t in range(0, len(tl_tracks)-maxsize)]}
            )

    def _trigger_end_of_tracklist_reached(self, station_id, auto_play=False):
        listener.PandoraFrontendListener.send('end_of_tracklist_reached', station_id=station_id, auto_play=auto_play)


@total_ordering
class MatchResult(object):
    def __init__(self, marker, ratio):
        super(MatchResult, self).__init__()

        self.marker = marker
        self.ratio = ratio

    def __eq__(self, other):
        return self.ratio == other.ratio

    def __lt__(self, other):
        return self.ratio < other.ratio

EventMarker = namedtuple('EventMarker', 'event, uri, time')


class EventMonitorFrontend(pykka.ThreadingActor,
                           core.CoreListener,
                           audio.AudioListener,
                           listener.PandoraFrontendListener,
                           listener.PandoraBackendListener,
                           listener.PandoraPlaybackListener,
                           listener.EventMonitorListener):

    def __init__(self, config, core):
        super(EventMonitorFrontend, self).__init__()
        self.core = core
        self.event_sequences = []
        self.sequence_match_results = None
        self._track_changed_marker = None
        self._monitor_lock = threading.Lock()

        self.config = config['pandora']
        self.is_active = self.config['event_support_enabled']

    def on_start(self):
        if not self.is_active:
            return

        interval = float(self.config['double_click_interval'])
        self.sequence_match_results = Queue.PriorityQueue(maxsize=4)

        self.event_sequences.append(EventSequence(self.config['on_pause_resume_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_resumed'], self.sequence_match_results,
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_resume_pause_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_resumed',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_previous_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_ended',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  wait_for='track_changed_previous',
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_next_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_ended',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  wait_for='track_changed_next',
                                                  interval=interval))

        self.trigger_events = set(e.target_sequence[0] for e in self.event_sequences)

    @only_execute_for_pandora_uris
    def on_event(self, event, **kwargs):
        if not self.is_active:
            return

        super(EventMonitorFrontend, self).on_event(event, **kwargs)
        self._detect_track_change(event, **kwargs)

        if self._monitor_lock.acquire(False):
            if event in self.trigger_events:
                # Monitor not running and current event will not trigger any starts either, ignore
                self.notify_all(event, uri=get_active_uri(self.core, event, **kwargs), **kwargs)
                self.monitor_sequences()
            else:
                self._monitor_lock.release()
                return
        else:
            # Just pass on the event
            self.notify_all(event, **kwargs)

    def notify_all(self, event, **kwargs):
        for es in self.event_sequences:
            es.notify(event, **kwargs)

    def _detect_track_change(self, event, **kwargs):
        if not self._track_changed_marker and event == 'track_playback_ended':
            self._track_changed_marker = EventMarker(event,
                                                     kwargs['tl_track'].track.uri,
                                                     int(time.time() * 1000))

        elif self._track_changed_marker and event in ['track_playback_paused', 'track_playback_started']:
            change_direction = self._get_track_change_direction(self._track_changed_marker)
            if change_direction:
                self._trigger_track_changed(change_direction,
                                            old_uri=self._track_changed_marker.uri,
                                            new_uri=kwargs['tl_track'].track.uri)
                self._track_changed_marker = None

    @run_async
    def monitor_sequences(self):
        for es in self.event_sequences:
            # Wait until all sequences have been processed
            es.wait()

        # Get the last item in the queue (will have highest ratio)
        match = None
        while not self.sequence_match_results.empty():
            match = self.sequence_match_results.get()
            self.sequence_match_results.task_done()

        if match and match.ratio == 1.0:
            if match.marker.uri and isinstance(PandoraUri.factory(match.marker.uri), AdItemUri):
                logger.info('Ignoring doubleclick event for Pandora advertisement...')
            else:
                self._trigger_event_triggered(match.marker.event, match.marker.uri)
            # Resume playback...
            if self.core.playback.get_state().get() != PlaybackState.PLAYING:
                self.core.playback.resume()

        self._monitor_lock.release()

    def event_processed(self, track_uri, pandora_event):
        if pandora_event == 'delete_station':
            self.core.tracklist.clear()

    def _get_track_change_direction(self, track_marker):
        history = self.core.history.get_history().get()
        for i, h in enumerate(history):
            # TODO: find a way to eliminate this timing disparity between when 'track_playback_ended' event for
            #       one track is processed, and the next track is added to the history.
            if h[0] + 100 < track_marker.time:
                if h[1].uri == track_marker.uri:
                    # This is the point in time in the history that the track was played.
                    if history[i-1][1].uri == track_marker.uri:
                        # Track was played again immediately.
                        # User either clicked 'previous' in consume mode or clicked 'stop' -> 'play' for same track.
                        # Both actions are interpreted as 'previous'.
                        return 'track_changed_previous'
                    else:
                        # Switched to another track, user clicked 'next'.
                        return 'track_changed_next'

    def _trigger_event_triggered(self, event, uri):
        (listener.EventMonitorListener.send('event_triggered',
                                            track_uri=uri,
                                            pandora_event=event))

    def _trigger_track_changed(self, track_change_event, old_uri, new_uri):
        (listener.EventMonitorListener.send(track_change_event,
                                            old_uri=old_uri,
                                            new_uri=new_uri))


class EventSequence(object):
    pykka_traversable = True

    def __init__(self, on_match_event, target_sequence, result_queue, interval=1.0, strict=False, wait_for=None):
        self.on_match_event = on_match_event
        self.target_sequence = target_sequence
        self.result_queue = result_queue
        self.interval = interval
        self.strict = strict
        self.wait_for = wait_for

        self.wait_for_event = threading.Event()
        if not self.wait_for:
            self.wait_for_event.set()

        self.events_seen = []
        self._timer = None
        self.target_uri = None

        self.monitoring_completed = threading.Event()
        self.monitoring_completed.set()

    @classmethod
    def match_sequence(cls, a, b):
        sm = SequenceMatcher(a=' '.join(a), b=' '.join(b))
        return sm.ratio()

    def notify(self, event, **kwargs):
        if self.is_monitoring():
            self.events_seen.append(event)
            if not self.wait_for_event.is_set() and self.wait_for == event:
                self.wait_for_event.set()

        elif self.target_sequence[0] == event:
            if kwargs.get('time_position', 0) == 0:
                # Don't do anything if track playback has not yet started.
                return
            else:
                self.start_monitor(kwargs.get('uri', None))
                self.events_seen.append(event)

    def is_monitoring(self):
        return not self.monitoring_completed.is_set()

    def start_monitor(self, uri):
        self.monitoring_completed.clear()

        self.target_uri = uri
        self._timer = threading.Timer(self.interval, self.stop_monitor, args=(self.interval,))
        self._timer.daemon = True
        self._timer.start()

    @run_async
    def stop_monitor(self, timeout):
        try:
            if self.strict:
                i = 0
                try:
                    for e in self.target_sequence:
                        i = self.events_seen[i:].index(e) + 1
                except ValueError:
                    # Make sure that we have seen every event in the target sequence, and in the right order
                    return
            elif not all([e in self.events_seen for e in self.target_sequence]):
                # Make sure that we have seen every event in the target sequence, ignoring order
                return
            if self.wait_for_event.wait(timeout=timeout):
                self.result_queue.put(
                    MatchResult(
                        EventMarker(self.on_match_event, self.target_uri, int(time.time() * 1000)),
                        self.get_ratio()
                    )
                )
        finally:
            self.reset()
            self.monitoring_completed.set()

    def reset(self):
        if self.wait_for:
            self.wait_for_event.clear()
        else:
            self.wait_for_event.set()

        self.events_seen = []

    def get_ratio(self):
        if self.wait_for:
            # Add 'wait_for' event as well to make ratio more accurate.
            match_sequence = self.target_sequence + [self.wait_for]
        else:
            match_sequence = self.target_sequence
        if self.strict:
            ratio = EventSequence.match_sequence(self.events_seen, match_sequence)
        else:
            filtered_list = [e for e in self.events_seen if e in match_sequence]
            ratio = EventSequence.match_sequence(filtered_list, match_sequence)
        if ratio < 1.0 and self.strict:
            return 0
        return ratio

    def wait(self, timeout=None):
        return self.monitoring_completed.wait(timeout=timeout)
