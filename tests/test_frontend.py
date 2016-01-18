from __future__ import absolute_import, division, print_function, unicode_literals

import Queue

import unittest

from mock import mock

from mopidy import core, listener, models

from mopidy.audio import PlaybackState

from mopidy.core import CoreListener

import pykka

from mopidy_pandora import frontend
from mopidy_pandora.frontend import PandoraFrontend
from mopidy_pandora.monitor import EventMonitor

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


class TestFrontend(BaseTest):
    def setUp(self):  # noqa: N802
        super(TestFrontend, self).setUp()
        self.frontend = frontend.PandoraFrontend.start(conftest.config(), self.core).proxy()

    def tearDown(self):  # noqa: N802
        super(TestFrontend, self).tearDown()

    def test_add_track_starts_playback(self):
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED
        self.core.tracklist.clear()
        self.frontend.add_track(self.tl_tracks[0].track, auto_play=True).get()

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        assert self.core.playback.get_current_track().get() == self.tl_tracks[0].track

    def test_add_track_trims_tracklist(self):
        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)

        # Remove first track so we can add it again
        self.core.tracklist.remove({'tlid': [self.tl_tracks[0].tlid]})

        self.frontend.add_track(self.tl_tracks[0].track).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 2
        assert tl_tracks[-1].track == self.tl_tracks[0].track

    def test_next_track_available_adds_track_to_playlist(self):
        self.core.tracklist.clear()
        self.core.tracklist.add(uris=[self.tl_tracks[0].track.uri])
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.replay_events(self.frontend, until='track_playback_started')

        self.frontend.next_track_available(self.tl_tracks[1].track, True).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()

        assert tl_tracks[-1].track == self.tl_tracks[1].track
        assert self.core.playback.get_current_track().get() == self.tl_tracks[1].track

    def test_next_track_available_forces_stop_if_no_more_tracks(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid)

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        self.frontend.next_track_available(None).get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_on_event_passes_on_calls_to_monitor(self):
        config = conftest.config()
        config['pandora']['event_support_enabled'] = True

        self.frontend = frontend.PandoraFrontend.start(config, self.core).proxy()

        assert self.frontend.event_monitor.core.get()
        monitor_mock = mock.Mock(spec=EventMonitor)
        self.frontend.event_monitor = monitor_mock
        self.frontend.on_event('track_playback_started', tl_track=self.core.tracklist.get_tl_tracks().get()[0]).get()
        assert monitor_mock.on_event.called

    def test_only_execute_for_pandora_does_not_execute_for_non_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[3].tlid)
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert not func_mock.called

    def test_only_execute_for_pandora_does_not_execute_for_malformed_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        tl_track_mock = mock.Mock(spec=models.TlTrack)
        track_mock = mock.Mock(spec=models.Track)
        track_mock.uri = 'pandora:invalid_uri'
        tl_track_mock.track = track_mock
        frontend.only_execute_for_pandora_uris(func_mock)(self, tl_track=tl_track_mock)

        assert not func_mock.called

    def test_only_execute_for_pandora_executes_for_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[0].tlid)
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert func_mock.called

    def test_options_changed_triggers_setup(self):
        with mock.patch.object(PandoraFrontend, 'set_options', mock.Mock()) as set_options_mock:
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.frontend.setup_required = False
            listener.send(CoreListener, 'options_changed')
            self.replay_events(self.frontend)
            assert set_options_mock.called

    def test_set_options_performs_auto_setup(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            assert self.frontend.setup_required.get()
            self.core.tracklist.set_repeat(True)
            self.core.tracklist.set_consume(False)
            self.core.tracklist.set_random(True)
            self.core.tracklist.set_single(True)
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.replay_events(self.frontend)

            thread_joiner.wait(timeout=1.0)

            assert self.core.tracklist.get_repeat().get() is False
            assert self.core.tracklist.get_consume().get() is True
            assert self.core.tracklist.get_random().get() is False
            assert self.core.tracklist.get_single().get() is False
            self.replay_events(self.frontend)

            assert not self.frontend.setup_required.get()

    def test_set_options_skips_auto_setup_if_not_configured(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        config = conftest.config()
        config['pandora']['auto_setup'] = False
        self.frontend.setup_required = True

        self.replay_events(self.frontend)
        assert self.frontend.setup_required

    def test_set_options_triggered_on_core_events(self):
        with mock.patch.object(PandoraFrontend, 'set_options', mock.Mock()) as set_options_mock:

            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            core_events = {
                'track_playback_started': {'tl_track': tl_tracks[0]},
                'track_playback_ended': {'tl_track': tl_tracks[0], 'time_position': 100},
                'track_playback_paused': {'tl_track': tl_tracks[0], 'time_position': 100},
                'track_playback_resumed': {'tl_track': tl_tracks[0], 'time_position': 100},
            }

            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

            for (event, kwargs) in core_events.items():
                self.frontend.setup_required = True
                listener.send(CoreListener, event, **kwargs)
                self.replay_events(self.frontend)
                self.assertEqual(set_options_mock.called, True, "Setup not done for event '{}'".format(event))
                set_options_mock.reset_mock()

    def test_skip_limit_exceed_stops_playback(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid)
        assert self.core.playback.get_state().get() == PlaybackState.PLAYING

        self.frontend.skip_limit_exceeded().get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_station_change_does_not_trim_currently_playing_track_from_tracklist(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            with mock.patch.object(PandoraFrontend, 'is_station_changed', mock.Mock(return_value=True)):

                self.core.tracklist.clear()
                self.core.tracklist.add(uris=[self.tl_tracks[0].track.uri])

                thread_joiner.wait(timeout=1.0)  # Wait until threads spawned by frontend have finished.

                tl_tracks = self.core.tracklist.get_tl_tracks().get()
                assert len(tl_tracks) == 1
                assert tl_tracks[0].track == self.tl_tracks[0].track

    def test_is_end_of_tracklist_reached(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid)

        assert not self.frontend.is_end_of_tracklist_reached().get()

    def test_event_support_disabled_does_not_initialize_monitor(self):
        assert not self.frontend.event_monitor.get()

    def test_is_end_of_tracklist_reached_last_track(self):
        self.core.playback.play(tlid=self.tl_tracks[-1].tlid)

        assert self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_no_tracks(self):
        self.core.tracklist.clear()

        assert self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_second_last_track(self):
        self.core.playback.play(tlid=self.tl_tracks[3].tlid)

        assert not self.frontend.is_end_of_tracklist_reached(self.tl_tracks[3].track).get()

    def test_is_station_changed(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid)
        self.core.playback.next()

        # Check against track of a different station
        assert self.frontend.is_station_changed(self.tl_tracks[4].track).get()

    def test_is_station_changed_no_history(self):
        assert not self.frontend.is_station_changed(self.tl_tracks[0].track).get()

    def test_changing_track_no_op(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.next()

            assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
            self.replay_events(self.frontend)

            thread_joiner.wait(timeout=1.0)  # Wait until threads spawned by frontend have finished.

            assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
            assert self.events.qsize() == 0

    def test_changing_track_station_changed(self):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            self.core.tracklist.clear()
            self.core.tracklist.add(uris=[self.tl_tracks[0].track.uri, self.tl_tracks[4].track.uri])
            assert len(self.core.tracklist.get_tl_tracks().get()) == 2

            self.core.playback.play(tlid=self.tl_tracks[0].tlid)
            self.core.playback.seek(100)
            self.replay_events(self.frontend)
            self.core.playback.next().get()

            self.replay_events(self.frontend, until='track_playback_started')

            thread_joiner.wait(timeout=1.0)  # Wait until threads spawned by frontend have finished.

            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            assert len(tl_tracks) == 1  # Tracks were trimmed from the tracklist
            # Only the track recently changed to is left in the tracklist
            assert tl_tracks[0].track.uri == self.tl_tracks[4].track.uri

            assert any(self.has_events([('end_of_tracklist_reached', {'station_id': 'id_mock_other',
                                                                      'auto_play': False})]))

    def test_track_unplayable_removes_tracks_from_tracklist(self):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        unplayable_track = tl_tracks[0]
        self.frontend.track_unplayable(unplayable_track.track).get()

        self.assertEqual(unplayable_track in self.core.tracklist.get_tl_tracks().get(), False)

    def test_track_unplayable_triggers_end_of_tracklist_event(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.replay_events(self.frontend)

        self.frontend.track_unplayable(self.tl_tracks[-1].track).get()
        assert all([self.has_events('end_of_tracklist_reached')])
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED
