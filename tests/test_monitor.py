from __future__ import absolute_import, division, print_function, unicode_literals

import Queue


import unittest

from mock import mock

from mopidy import core, models

import pykka
import pytest

from mopidy_pandora import monitor
from mopidy_pandora.monitor import EventSequence

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
                listener.on_event(event, **kwargs).get()
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
        self.monitor = monitor.EventMonitor.start(conftest.config(), self.core).proxy()

        es1 = EventSequence('delete_station', ['track_playback_paused', 'track_playback_resumed', 'track_playback_paused'])
        es2 = EventSequence('thumbs_up', ['track_playback_paused', 'track_playback_resumed'])
        es3 = EventSequence('thumbs_down', ['track_playback_paused', 'track_playback_ended', 'track_playback_resumed'])
        es4 = EventSequence('sleep', ['track_playback_paused', 'track_playback_ended', 'track_playback_resumed'])

    es_list = [es1, es2, es3, es4]

        for es in EventMonitorTest.es_list:
            self.monitor.add_event_sequence(es).get()

    def tearDown(self):  # noqa: N802
        super(EventMonitorTest, self).tearDown()

    def test_events_processed_on_resume_action(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume().get()
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_resume_click']
            })]))

    def test_events_processed_on_triple_click_action(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume -> Pause
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume()
            self.core.playback.pause().get()
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=1.0)
            assert all(self.has_events([('event_triggered', {
                'track_uri': self.tl_tracks[0].track.uri,
                'pandora_event': conftest.config()['pandora']['on_pause_resume_pause_click']
            })]))

    def test_process_event_ignores_ads(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            self.core.playback.play(tlid=self.tl_tracks[2].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume().get()
            self.replay_events(self.monitor)

            thread_joiner.wait(timeout=1.0)
            assert self.events.qsize() == 0  # Check that no events were triggered

    def test_process_event_resets_event_marker(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            with pytest.raises(KeyError):
                self.core.playback.play(tlid=self.tl_tracks[0].tlid)
                self.core.playback.seek(100)
                self.core.playback.pause()
                self.core.playback.resume().get()
                self.replay_events(self.monitor)

                thread_joiner.wait(timeout=self.monitor.double_click_interval.get() + 1)
                self.monitor.get_event_marker('track_playback_paused').get()

    def test_process_event_handles_exception(self):
        with mock.patch.object(monitor.EventMonitor, '_get_event',
                               mock.PropertyMock(return_value=None, side_effect=KeyError('error_mock'))):
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.core.playback.pause()
            self.core.playback.resume().get()
            self.replay_events(self.monitor)

            assert self.events.qsize() == 0  # Check that no events were triggered

    def test_trigger_starts_double_click_timer(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid)
        self.core.playback.seek(100)
        self.core.playback.pause().get()
        self.replay_events(self.monitor)

        assert self.monitor.get_event_marker('track_playback_paused').get().time > 0

    def test_trigger_does_not_start_timer_at_track_start(self):
        with pytest.raises(KeyError):
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.pause().get()
            self.replay_events(self.monitor)

            assert self.monitor.get_event_marker('track_playback_paused').get()


def test_match_sequence_on_longest():
    es1 = EventSequence('match_event_1', ['e1'])
    es2 = EventSequence('match_event_1', ['e1', 'e2'])
    es3 = EventSequence('match_event_1', ['e1', 'e2', 'e3'])

    es_list = [es1, es2, es3]

    es1.events_seen = ['e1']
    es2.events_seen = ['e1', 'e2']
    es3.events_seen = ['e1', 'e2', 'e3']

    assert es1 in EventSequence.match_sequence_list(es_list)


def test_match_sequence_strict():
    es_list = [EventSequence('match_event_1', ['e1', 'e2', 'e3'], True)]
    assert EventSequence.match_sequence_list(es_list, ['e1', 'e3']) is None


def test_match_sequence_partial():
    es1 = EventSequence('match_event_1', ['e1', 'e3'])
    es2 = EventSequence('match_event_1', ['e1', 'e2', 'e3'])
    es3 = EventSequence('match_event_1', ['e1', 'e2', 'e3', 'e4'])

    es_list = [es1, es2, es3]

    assert EventSequence.match_sequence_list(es_list, ['e1', 'e3']) == es1
    assert EventSequence.match_sequence_list(es_list, ['e1', 'e2', 'e3']) == es2
    assert EventSequence.match_sequence_list(es_list, ['e1', 'e3', 'e4']) == es3
