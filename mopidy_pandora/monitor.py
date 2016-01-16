from __future__ import absolute_import, division, print_function, unicode_literals

import Queue

import logging

import threading

import time

from collections import namedtuple

from difflib import SequenceMatcher

from functools import total_ordering

from mopidy import core
from mopidy.audio import PlaybackState

from mopidy_pandora import listener
from mopidy_pandora.uri import AdItemUri, PandoraUri
from mopidy_pandora.utils import run_async

logger = logging.getLogger(__name__)

EventMarker = namedtuple('EventMarker', 'event, uri, time')


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


class EventMonitor(core.CoreListener,
                   listener.PandoraBackendListener,
                   listener.PandoraPlaybackListener,
                   listener.PandoraFrontendListener,
                   listener.EventMonitorListener):

    pykka_traversable = True

    def __init__(self, config, core):
        super(EventMonitor, self).__init__()
        self.core = core
        self.event_sequences = []
        self.sequence_match_results = None
        self._track_changed_marker = None
        self._monitor_lock = threading.Lock()

        self.config = config['pandora']
        self.on_start()

    def on_start(self):
        interval = float(self.config['double_click_interval'])
        self.sequence_match_results = Queue.PriorityQueue(maxsize=4)

        self.event_sequences.append(EventSequence(self.config['on_pause_resume_click'],
                                                  ['track_playback_paused',
                                                   'playback_state_changed',
                                                   'track_playback_resumed'], self.sequence_match_results,
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_resume_pause_click'],
                                                  ['track_playback_paused',
                                                   'playback_state_changed',
                                                   'track_playback_resumed',
                                                   'playback_state_changed',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_previous_click'],
                                                  ['track_playback_paused',
                                                   'playback_state_changed',
                                                   'track_playback_ended',
                                                   'track_changing',
                                                   'playback_state_changed',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  wait_for='track_changed_previous',
                                                  interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_next_click'],
                                                  ['track_playback_paused',
                                                   'playback_state_changed',
                                                   'track_playback_ended',
                                                   'track_changing',
                                                   'playback_state_changed',
                                                   'track_playback_paused'], self.sequence_match_results,
                                                  wait_for='track_changed_next',
                                                  interval=interval))

        self.trigger_events = set(e.target_sequence[0] for e in self.event_sequences)

    def on_event(self, event, **kwargs):
        super(EventMonitor, self).on_event(event, **kwargs)
        self._detect_track_change(event, **kwargs)

        if self._monitor_lock.acquire(False):
            if event in self.trigger_events:
                # Monitor not running and current event will not trigger any starts either, ignore
                self.notify_all(event, **kwargs)
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
            try:
                change_direction = self._get_track_change_direction(self._track_changed_marker)
                if change_direction:
                    self._trigger_track_changed(change_direction,
                                                old_uri=self._track_changed_marker.uri,
                                                new_uri=kwargs['tl_track'].track.uri)
                    self._track_changed_marker = None
            except KeyError:
                # Must be playing the first track, ignore
                pass

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

        if match and match.ratio >= 0.80:
            if match.marker.uri and type(PandoraUri.factory(match.marker.uri)) is AdItemUri:
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
                    if i == 0:
                        return None
                    if history[i-1][1].uri == track_marker.uri:
                        # Track was played again immediately.
                        # User clicked 'previous' in consume mode.
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
                tl_track = kwargs.get('tl_track', None)
                uri = None
                if tl_track:
                    uri = tl_track.track.uri
                self.start_monitor(uri)
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
            self.target_sequence.append(self.wait_for)
        ratio = EventSequence.match_sequence(self.events_seen, self.target_sequence)
        if ratio < 1.0 and self.strict:
            return 0
        return ratio

    def wait(self, timeout=None):
        return self.monitoring_completed.wait(timeout=timeout)
