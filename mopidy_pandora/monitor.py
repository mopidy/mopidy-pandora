from __future__ import absolute_import, division, print_function, unicode_literals
import Queue

import logging

import threading

import time

from collections import namedtuple

from difflib import SequenceMatcher

from mopidy import core
from mopidy.audio import PlaybackState

import pykka

from mopidy_pandora import listener
from mopidy_pandora.frontend import only_execute_for_pandora_uris
from mopidy_pandora.uri import AdItemUri, PandoraUri
from mopidy_pandora.utils import run_async

logger = logging.getLogger(__name__)

EventMarker = namedtuple('EventMarker', 'event, uri, time')

class EventMonitor(pykka.ThreadingActor, core.CoreListener,
                   listener.PandoraBackendListener,
                   listener.PandoraPlaybackListener,
                   listener.PandoraFrontendListener):

    def __init__(self, config, core):
        super(EventMonitor, self).__init__()

        self.core = core
        self.event_sequences = []
        self.monitor_running_event = threading.Event()
        self.monitor_running_event.clear()
        self._track_changed_marker = None

        self.config = config['pandora']

    def on_start(self):
        interval = float(self.config['double_click_interval'])
        self.event_sequences.append(EventSequence(self.config['on_pause_resume_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_resumed'], self, interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_resume_pause_click'],
                                                  ['track_playback_paused',
                                                   'track_playback_resumed',
                                                   'track_playback_paused'], self, interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_previous_click'],
                                                  ['track_playback_paused',
                                                   'preparing_track'], self,
                                                  wait_for='track_changed_previous', interval=interval))

        self.event_sequences.append(EventSequence(self.config['on_pause_next_click'],
                                                  ['track_playback_paused',
                                                   'preparing_track'], self,
                                                  wait_for='track_changed_next', interval=interval))

        self.sequence_match_results = Queue.Queue(maxsize=len(self.event_sequences))

    @only_execute_for_pandora_uris
    def on_event(self, event, **kwargs):
        # Check if this event is covered by one of the defined event sequences
        for es in self.event_sequences:
            es.notify(event, **kwargs)

        self._detect_track_change(event, **kwargs)

    def sequence_stopped(self):
        if not any([es.is_running() for es in self.event_sequences]):
            self.all_stopped.set()


        self.sequence_match_results.put(result_tup)
        if self.sequence_match_results.full():
            ratios = []
            self.sequence_match_results.join()
            while True:
                try:
                    ratios.append(self.sequence_match_results.get_nowait())
                    self.sequence_match_results.task_done()
                except Queue.Empty:
                    ratios.sort(key=lambda es: es.get_ratio())
                    self._trigger_event_triggered(ratios[0].on_match_event, ratios[0].target_uri)

    # @classmethod
    # def priority_match(cls, es_list):
    #     ratios = []
    #     for es in es_list:
    #         ratios.append((es, es.get_ratio()))
    #
    #     ratios.sort(key=lambda tup: tup[1])
    #     if ratios[-1][0].strict and ratios[-1][1] != 1.0:
    #         return []
    #
    #     return [r[0] for r in ratios if r[0] >= ratios[-1][0]]

    def _detect_track_change(self, event, **kwargs):
        if event == 'track_playback_ended':
            self._track_changed_marker = EventMarker('track_playback_ended',
                                                     kwargs['tl_track'].track.uri,
                                                     int(time.time() * 1000))

        elif event in ['track_playback_started', 'track_playback_resumed']:
            try:
                change_direction = self._get_track_change_direction(self._track_changed_marker)
                self._trigger_track_changed(change_direction,
                                            old_uri=self._track_changed_marker.uri,
                                            new_uri=kwargs['tl_track'].track.uri)
            except KeyError:
                # Must be playing the first track, ignore
                pass

    def process_event(self, event):
        try:
            event = self._get_track_change_direction(event)
        except KeyError:
            logger.exception("Error processing Pandora event '{}', ignoring...".format(event))
            return
        else:
            self._trigger_event_triggered(event, self._event_markers.uri)
            # Resume playback...
            if event == 'change_track' and self.core.playback.get_state().get() != PlaybackState.PLAYING:
                self.core.playback.resume()

    def _get_track_change_direction(self, track_marker):
        history = self.core.history.get_history().get()
        for i, h in enumerate(history):
            if h[0] < track_marker.time:
                if h[1].uri == track_marker.uri:
                    # This is the point in time in the history that the track was played.
                    if history[i-1][1].uri == track_marker.uri:
                        # Track was played again immediately.
                        # User clicked 'previous' in consume mode.
                        return 'track_changed_previous'
                    else:
                        # Switched to another track, user clicked 'next'.
                        return 'track_changed_next'

    def _trigger_event_triggered(self, event, uri):
        (listener.PandoraEventHandlingFrontendListener.send('event_triggered',
                                                            track_uri=uri,
                                                            pandora_event=event))

    def _trigger_track_changed(self, track_change_event, old_uri, new_uri):
        (listener.EventMonitorListener.send(track_change_event,
                                            old_uri=old_uri,
                                            new_uri=new_uri))


class EventSequence(object):
    pykka_traversable = True

    def __init__(self, on_match_event, target_sequence, monitor, interval=1.0, strict=False, wait_for=None):
        self.on_match_event = on_match_event
        self.target_sequence = target_sequence
        self.monitor = monitor
        self.interval = interval
        self.strict = strict
        self.wait_for = wait_for

        self.wait_for_event = threading.Event()
        if not self.wait_for:
            self.wait_for_event.set()

        self.events_seen = []
        self._timer = None
        self.target_uri = None

    @classmethod
    def match_sequence_list(cls, a, b):
        sm = SequenceMatcher(a=' '.join(a), b=' '.join(b))
        return sm.ratio()

    def notify(self, event, **kwargs):
        if self.is_running():
            self.events_seen.append(event)
        elif self.target_sequence[0] == event:
            if kwargs.get('time_position', 0) == 0:
                # Don't do anything if track playback has not yet started.
                return
            else:
                tl_track = kwargs.get('tl_track', None)
                if tl_track:
                    uri = tl_track.track.uri
                else:
                    uri = None
                self.start_monitor(uri)

        if not self.wait_for_event.is_set() and self.wait_for == event:
            self.wait_for_event.set()

    def is_running(self):
        return (self._timer and self._timer.is_alive()) or not self.wait_for_event.is_set()

    def start_monitor(self, uri):
        # TODO: ad checking probably belongs somewhere else.
        if type(PandoraUri.factory(uri)) is AdItemUri:
            logger.info('Ignoring doubleclick event for Pandora advertisement...')
            return

        self.target_uri = uri
        self._timer = threading.Timer(self.interval, self.stop_monitor)
        self._timer.daemon = True
        self._timer.start()

    @run_async
    def stop_monitor(self):
        if self.wait_for_event.wait(timeout=60):
            self.monitor.sequence_stopped()

    def reset(self):
        self.wait_for_event.set()
        self.events_seen = []
        self._timer = None

    def get_ratio(self):
        ratio = EventSequence.match_sequence_list(self.events_seen, self.target_sequence)
        if ratio < 1.0 and self.strict:
            return 0
        return ratio
