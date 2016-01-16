from __future__ import absolute_import, division, print_function, unicode_literals

import Queue

import time

import unittest

from mock import mock

from mopidy import core, listener, models

import pykka

from mopidy_pandora import monitor

from mopidy_pandora.listener import PandoraPlaybackListener

from mopidy_pandora.monitor import EventMarker, EventSequence, MatchResult

from tests import conftest, dummy_backend

from tests.dummy_backend import DummyBackend, DummyPandoraBackend


class BaseTest(unittest.TestCase):
    tracks = [
        models.Track(uri='pandora:track:id_mock:token_mock1', length=40000),  # Regular track
        models.Track(uri='pandora:track:id_mock:token_mock2', length=40000),  # Regular track
        models.Track(uri='pandora:ad:id_mock:token_mock3', length=40000),  # Advertisement
        models.Track(uri='mock:track:id_mock:token_mock4', length=40000),  # Not a pandora track
        models.Track(uri='pandora:track:id_mock_other:token_mock5', length=40000),  # Different station
        models.Track(uri='pandora:track:id_mock:token_mock6', length=None),  # No duration
    ]

    uris = [
        'pandora:track:id_mock:token_mock1', 'pandora:track:id_mock:token_mock2',
        'pandora:ad:id_mock:token_mock3', 'mock:track:id_mock:token_mock4',
        'pandora:track:id_mock_other:token_mock5', 'pandora:track:id_mock:token_mock6']

    def setUp(self):
        config = {'core': {'max_tracklist_length': 10000}}

        self.backend = dummy_backend.create_proxy(DummyPandoraBackend)
        self.non_pandora_backend = dummy_backend.create_proxy(DummyBackend)

        self.core = core.Core.start(
            config, backends=[self.backend, self.non_pandora_backend]).proxy()

        def lookup(uris):
            result = {uri: [] for uri in uris}
            for track in self.tracks:
                if track.uri in result:
                    result[track.uri].append(track)
            return result

        self.core.library.lookup = lookup
        self.tl_tracks = self.core.tracklist.add(uris=self.uris).get()

        self.events = Queue.Queue()
        self.patcher = mock.patch('mopidy.listener.send')
        self.core_patcher = mock.patch('mopidy.listener.send_async')

        self.send_mock = self.patcher.start()
        self.core_send_mock = self.core_patcher.start()

        def send(cls, event, **kwargs):
            self.events.put((event, kwargs))

        self.send_mock.side_effect = send
        self.core_send_mock.side_effect = send

    def tearDown(self):
        pykka.ActorRegistry.stop_all()
        mock.patch.stopall()

    def replay_events(self, listener, until=None):
        while True:
            try:
                e = self.events.get(timeout=0.1)
                event, kwargs = e
                listener.on_event(event, **kwargs)
                if e[0] == until:
                    break
            except Queue.Empty:
                # All events replayed.
                break

    def has_events(self, events):
        q = []
        while True:
            try:
                q.append(self.events.get(timeout=0.1))
            except Queue.Empty:
                # All events replayed.
                break

        return [e in q for e in events]


class EventMonitorTest(BaseTest):
    def setUp(self):  # noqa: N802
        super(EventMonitorTest, self).setUp()
        self.monitor = monitor.EventMonitor(conftest.config(), self.core)
        # Consume more needs to be enabled to detect 'previous' track changes
        self.core.tracklist.set_consume(True)

    def test_detect_track_change_next(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.replay_events(self.monitor)
            self.core.playback.next().get()
            self.replay_events(self.monitor, until='track_playback_started')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('track_changed_next', {
                'old_uri': self.tl_tracks[0].track.uri,
                'new_uri': self.tl_tracks[1].track.uri
            })]))

    def test_detect_track_change_next_from_paused(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause().get()
            self.replay_events(self.monitor)
            self.core.playback.next().get()
            self.replay_events(self.monitor, until='track_playback_paused')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('track_changed_next', {
                'old_uri': self.tl_tracks[0].track.uri,
                'new_uri': self.tl_tracks[1].track.uri
            })]))

    def test_detect_track_change_previous(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100).get()
            self.replay_events(self.monitor)
            self.core.playback.previous().get()
            self.replay_events(self.monitor, until='track_playback_started')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('track_changed_previous', {
                'old_uri': self.tl_tracks[0].track.uri,
                'new_uri': self.tl_tracks[0].track.uri
            })]))

    def test_detect_track_change_previous_from_paused(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause().get()
            self.replay_events(self.monitor)
            self.core.playback.previous().get()
            self.replay_events(self.monitor, until='track_playback_paused')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('track_changed_previous', {
                'old_uri': self.tl_tracks[0].track.uri,
                'new_uri': self.tl_tracks[0].track.uri
            })]))

    def test_events_triggered_on_next_action(self):
        with conftest.ThreadJoiner(timeout=10.0) as thread_joiner:
            # Pause -> Next
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause().get()
            self.replay_events(self.monitor)
            self.core.playback.next().get()
            listener.send(PandoraPlaybackListener, 'track_changing', track=self.tl_tracks[1].track)
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=10.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_next_click']
            })]))

    def test_events_triggered_on_previous_action(self):
        with conftest.ThreadJoiner(timeout=10.0) as thread_joiner:
            # Pause -> Previous
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause().get()
            self.replay_events(self.monitor)
            self.core.playback.previous().get()
            listener.send(PandoraPlaybackListener, 'track_changing', track=self.tl_tracks[0].track)
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=10.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_previous_click']
            })]))

    def test_events_triggered_on_resume_action(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume().get()
            self.replay_events(self.monitor, until='track_playback_resumed')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_resume_click']
            })]))

    def test_events_triggered_on_triple_click_action(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume -> Pause
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume()
            self.replay_events(self.monitor)
            self.core.playback.pause().get()
            self.replay_events(self.monitor, until='track_playback_resumed')

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_resume_pause_click']
            })]))

    def test_monitor_ignores_ads(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            self.core.playback.play(tlid=self.tl_tracks[2].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume().get()
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=1.0)
            assert self.events.qsize() == 0  # Check that no events were triggered

    # TODO: Add this test back again
    # def test_process_event_resumes_playback_for_change_track(self):
    #     actions = ['stop', 'change_track', 'resume']
    #
    #     for action in actions:
    #         self.events = Queue.Queue()  # Make sure that the queue is empty
    #         self.core.playback.play(tlid=self.tl_tracks[0].tlid)
    #         self.core.playback.seek(100)
    #         self.core.playback.pause().get()
    #         self.replay_events(self.frontend)
    #         assert self.core.playback.get_state().get() == PlaybackState.PAUSED
    #
    #         if action == 'change_track':
    #             self.core.playback.next()
    #             self.frontend.process_event(event=action).get()
    #
    #             self.assertEqual(self.core.playback.get_state().get(),
    #                              PlaybackState.PLAYING,
    #                              "Failed to set playback for action '{}'".format(action))
    #         else:
    #             self.frontend.process_event(event=action).get()
    #             self.assertEqual(self.core.playback.get_state().get(),
    #                              PlaybackState.PAUSED,
    #                              "Failed to set playback for action '{}'".format(action))


class EventSequenceTest(unittest.TestCase):

    def setUp(self):
        self.rq = Queue.PriorityQueue()
        self.es = EventSequence('match_mock', ['e1', 'e2', 'e3'], self.rq, 0.1, False)
        self.es_strict = EventSequence('match_mock', ['e1', 'e2', 'e3'], self.rq, 0.1, True)
        self.es_wait = EventSequence('match_mock', ['e1', 'e2', 'e3'], self.rq, 0.1, False, 'w1')

        self.event_sequences = [self.es, self.es_strict, self.es_wait]

        track_mock = mock.Mock(spec=models.Track)
        track_mock.uri = 'pandora:track:id_mock:token_mock'
        self.tl_track_mock = mock.Mock(spec=models.TlTrack)
        self.tl_track_mock.track = track_mock

    def test_events_ignored_if_time_position_is_zero(self):
        for es in self.event_sequences:
            es.notify('e1')
        for es in self.event_sequences:
            assert not es.is_monitoring()

    def test_start_monitor_on_event(self):
        for es in self.event_sequences:
            es.notify('e1', tl_track=self.tl_track_mock, time_position=100)
        for es in self.event_sequences:
            assert es.is_monitoring()

    def test_start_monitor_handles_no_tl_track(self):
        for es in self.event_sequences:
            es.notify('e1', time_position=100)
        for es in self.event_sequences:
            assert es.is_monitoring()

    def test_stop_monitor_adds_result_to_queue(self):
        for es in self.event_sequences[0:2]:
            es.notify('e1', time_position=100)
            es.notify('e2', time_position=100)
            es.notify('e3', time_position=100)

        for es in self.event_sequences[0:2]:
            es.wait(1.0)
            assert not es.is_monitoring()

        assert self.rq.qsize() == 2

    def test_stop_monitor_only_waits_for_matched_events(self):
        self.es_wait.notify('e1', time_position=100)
        self.es_wait.notify('e_not_in_monitored_sequence', time_position=100)

        time.sleep(0.1 * 1.1)
        assert not self.es_wait.is_monitoring()
        assert self.rq.qsize() == 0

    def test_stop_monitor_waits_for_event(self):
        self.es_wait.notify('e1', time_position=100)
        self.es_wait.notify('e2', time_position=100)
        self.es_wait.notify('e3', time_position=100)

        assert self.es_wait.is_monitoring()
        assert self.rq.qsize() == 0

        self.es_wait.notify('w1', time_position=100)
        self.es_wait.wait(timeout=1.0)

        assert not self.es_wait.is_monitoring()
        assert self.rq.qsize() == 1

    def test_get_stop_monitor_that_all_events_occurred(self):
        self.es.notify('e1', time_position=100)
        self.es.notify('e2', time_position=100)
        self.es.notify('e3', time_position=100)
        assert self.rq.qsize() == 0

        self.es.wait(timeout=1.0)
        self.es.events_seen = ['e1', 'e2', 'e3']
        assert self.rq.qsize() > 0

    def test_get_stop_monitor_that_events_were_seen_in_order(self):
        self.es.notify('e1', time_position=100)
        self.es.notify('e3', time_position=100)
        self.es.notify('e2', time_position=100)
        self.es.wait(timeout=1.0)
        assert self.rq.qsize() == 0

        self.es.notify('e1', time_position=100)
        self.es.notify('e2', time_position=100)
        self.es.notify('e3', time_position=100)
        self.es.wait(timeout=1.0)
        assert self.rq.qsize() > 0

    def test_get_ratio_handles_repeating_events(self):
        self.es.target_sequence = ['e1', 'e2', 'e3', 'e1']
        self.es.events_seen = ['e1', 'e2', 'e3', 'e1']
        assert self.es.get_ratio() > 0

    def test_get_ratio_enforces_strict_matching(self):
        self.es_strict.events_seen = ['e1', 'e2', 'e3', 'e4']
        assert self.es_strict.get_ratio() == 0

        self.es_strict.events_seen = ['e1', 'e2', 'e3']
        assert self.es_strict.get_ratio() == 1


class MatchResultTest(unittest.TestCase):

    def test_match_result_comparison(self):

        mr1 = MatchResult(EventMarker('e1', 'u1', 0), 1)
        mr2 = MatchResult(EventMarker('e1', 'u1', 0), 2)

        assert mr1 < mr2
        assert mr2 > mr1
        assert mr1 != mr2

        mr2.ratio = 1
        assert mr1 == mr2
