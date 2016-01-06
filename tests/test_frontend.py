from __future__ import absolute_import, division, print_function, unicode_literals

import time

import unittest

from mock import mock

from mopidy import core, listener, models

from mopidy.audio import PlaybackState
from mopidy.core import CoreListener

import pykka

from mopidy_pandora import frontend
from mopidy_pandora.frontend import EventHandlingPandoraFrontend, PandoraFrontend

from tests import conftest, dummy_backend
from tests.dummy_backend import DummyBackend, DummyPandoraBackend


class TestPandoraFrontendFactory(unittest.TestCase):
    def test_events_supported_returns_event_handler_frontend(self):
        config = conftest.config()
        config['pandora']['event_support_enabled'] = True
        f = frontend.PandoraFrontendFactory(config, mock.PropertyMock())

        assert type(f) is frontend.EventHandlingPandoraFrontend

    def test_events_not_supported_returns_regular_frontend(self):
        config = conftest.config()
        config['pandora']['event_support_enabled'] = False
        f = frontend.PandoraFrontendFactory(config, mock.PropertyMock())

        assert type(f) is frontend.PandoraFrontend


class BaseTest(unittest.TestCase):
    tracks = [
        models.Track(uri='pandora:track:id_mock:token_mock1', length=40000),  # Regular track
        models.Track(uri='pandora:ad:id_mock:token_mock2', length=40000),  # Advertisement
        models.Track(uri='mock:track:id_mock:token_mock3', length=40000),  # Not a pandora track
        models.Track(uri='pandora:track:id_mock_other:token_mock4', length=40000),  # Different station
        models.Track(uri='pandora:track:id_mock:token_mock5', length=None),  # No duration
    ]

    uris = [
        'pandora:track:id_mock:token_mock1', 'pandora:ad:id_mock:token_mock2',
        'mock:track:id_mock:token_mock3', 'pandora:track:id_mock_other:token_mock4',
        'pandora:track:id_mock:token_mock5']

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

        self.events = []
        self.patcher = mock.patch('mopidy.listener.send')
        self.send_mock = self.patcher.start()

        def send(cls, event, **kwargs):
            self.events.append((event, kwargs))

        self.send_mock.side_effect = send

    def tearDown(self):
        pykka.ActorRegistry.stop_all()
        self.patcher.stop()

    def replay_events(self, frontend, until=None):
        while self.events:
            if self.events[0][0] == until:
                break
            event, kwargs = self.events.pop(0)
            frontend.on_event(event, **kwargs).get()


class TestFrontend(BaseTest):
    def setUp(self):  # noqa: N802
        super(TestFrontend, self).setUp()
        self.frontend = frontend.PandoraFrontend.start(conftest.config(), self.core).proxy()

    def tearDown(self):  # noqa: N802
        super(TestFrontend, self).tearDown()

    def test_add_track_starts_playback(self):
        new_track = models.Track(uri='pandora:track:id_mock:new_token_mock', length=40000)
        self.tracks.append(new_track)  # Add to internal list for lookup to work

        assert self.core.playback.get_state().get() == PlaybackState.STOPPED
        self.frontend.add_track(new_track, auto_play=True).get()

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        assert self.core.playback.get_current_track().get() == new_track

    def test_add_track_trims_tracklist(self):
        new_track = models.Track(uri='pandora:track:id_mock:new_token_mock', length=40000)
        self.tracks.append(new_track)  # Add to internal list for lookup to work

        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
        self.frontend.add_track(new_track).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 2
        assert tl_tracks[-1].track == new_track

    def test_only_execute_for_pandora_executes_for_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert func_mock.called

    def test_next_track_available_adds_track_to_playlist(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        new_track = models.Track(uri='pandora:track:id_mock:new_token_mock', length=40000)
        self.tracks.append(new_track)  # Add to internal list for lookup to work

        self.frontend.next_track_available(new_track, True).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert tl_tracks[-1].track == new_track
        assert self.core.playback.get_current_track().get() == new_track

    def test_next_track_available_forces_stop_if_no_more_tracks(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        self.frontend.next_track_available(None).get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_only_execute_for_pandora_does_not_execute_for_non_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[2].tlid).get()
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert not func_mock.called

    def test_options_changed_requires_setup(self):
        self.frontend.setup_required = False
        listener.send(CoreListener, 'options_changed')
        self.replay_events(self.frontend)
        assert self.frontend.setup_required.get()

    def test_set_options_performs_auto_setup(self):
        self.core.tracklist.set_repeat(True).get()
        self.core.tracklist.set_consume(False).get()
        self.core.tracklist.set_random(True).get()
        self.core.tracklist.set_single(True).get()
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert self.frontend.setup_required.get()
        self.frontend.set_options().get()
        assert self.core.tracklist.get_repeat().get() is False
        assert self.core.tracklist.get_consume().get() is True
        assert self.core.tracklist.get_random().get() is False
        assert self.core.tracklist.get_single().get() is False
        assert not self.frontend.setup_required.get()

    def test_set_options_skips_auto_setup_if_not_configured(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        config = conftest.config()
        config['pandora']['auto_setup'] = False
        self.frontend = frontend.PandoraFrontend.start(config, self.core).proxy()
        self.frontend.setup_required = True

        self.frontend.set_options().get()
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
                set_options_mock.reset()

    def test_skip_limit_exceed_stops_playback(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        assert self.core.playback.get_state().get() == PlaybackState.PLAYING

        self.frontend.skip_limit_exceeded().get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_is_end_of_tracklist_reached(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert not self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_last_track(self):
        self.core.playback.play(tlid=self.tl_tracks[4].tlid).get()

        assert self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_no_tracks(self):
        self.core.tracklist.clear().get()

        assert self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_second_last_track(self):
        self.core.playback.play(tlid=self.tl_tracks[3].tlid).get()

        assert not self.frontend.is_end_of_tracklist_reached(self.tl_tracks[3].track).get()

    def test_is_station_changed(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.next().get()  # Add track to history

        assert self.frontend.is_station_changed(self.tl_tracks[3].track).get()

    def test_is_station_changed_no_history(self):
        assert not self.frontend.is_station_changed(self.tl_tracks[0].track).get()

    def test_track_changed_no_op(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.next().get()  # Add track to history

        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)

        self.frontend.track_changed(self.tl_tracks[1].track).get()
        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
        assert len(self.events) == 0

    def test_track_changed_station_changed(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.next().get()  # Add track to history

        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)

        self.frontend.track_changed(self.tl_tracks[3].track).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 1  # Tracks were trimmed from the tracklist
        assert tl_tracks[0] == self.tl_tracks[3]  # Only the track recently changed to is left in the tracklist

        assert self.events[0] == ('end_of_tracklist_reached', {'station_id': 'id_mock_other', 'auto_play': False})

    def test_track_unplayable_removes_tracks_from_tracklist(self):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        unplayable_track = tl_tracks[0]
        self.frontend.track_unplayable(unplayable_track.track).get()

        self.assertEqual(unplayable_track in self.core.tracklist.get_tl_tracks().get(), False)

    def test_track_unplayable_triggers_end_of_tracklist_event(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        self.frontend.track_unplayable(self.tl_tracks[-1].track).get()
        is_event = [e[0] == 'end_of_tracklist_reached' for e in self.events]

        assert any(is_event)
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED


class TestEventHandlingFrontend(BaseTest):
    def setUp(self):  # noqa: N802
        super(TestEventHandlingFrontend, self).setUp()
        self.frontend = frontend.EventHandlingPandoraFrontend.start(conftest.config(), self.core).proxy()

    def tearDown(self):  # noqa: N802
        super(TestEventHandlingFrontend, self).tearDown()

    def test_events_check_for_doubleclick(self):
        with mock.patch.object(EventHandlingPandoraFrontend, 'check_doubleclicked', mock.Mock()) as click_mock:

            click_mock.return_value = False

            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            core_events = {
                'track_playback_ended': {'tl_track': tl_tracks[0], 'time_position': 100},
                'track_playback_resumed': {'tl_track': tl_tracks[0], 'time_position': 100},
                'track_changed': {'track': tl_tracks[0].track},
            }

            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

            for (event, kwargs) in core_events.items():
                self.frontend.set_click_time().get()
                listener.send(CoreListener, event, **kwargs)
                self.replay_events(self.frontend)
                self.assertEqual(click_mock.called, True, "Doubleclick not checked for event '{}'".format(event))
                click_mock.reset()

    def test_process_events_ignores_ads(self):
        self.core.playback.play(tlid=self.tl_tracks[1].tlid).get()

        self.frontend.check_doubleclicked(action='resume').get()
        assert len(self.events) == 0  # Check that no events were triggered

    def test_pause_starts_double_click_timer(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert self.frontend.get_click_time().get() == 0
        self.frontend.track_playback_paused(mock.Mock(), 100).get()
        assert self.frontend.get_click_time().get() > 0

    def test_pause_does_not_start_timer_at_track_start(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert self.frontend.get_click_time().get() == 0
        self.frontend.track_playback_paused(mock.Mock(), 0).get()
        assert self.frontend.get_click_time().get() == 0

    def test_process_events_handles_exception(self):
        with mock.patch.object(frontend.EventHandlingPandoraFrontend, '_get_event_targets',
                               mock.PropertyMock(return_value=None, side_effect=ValueError('error_mock'))):
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

            self.frontend._trigger_event_triggered = mock.PropertyMock()
            self.frontend.check_doubleclicked(action='resume').get()

        assert len(self.events) == 0  # Check that no events were triggered

    def test_wait_for_track_change_processes_stop_event(self):
        with mock.patch.object(EventHandlingPandoraFrontend, '_process_event', mock.Mock()) as mock_process_event:

            self.frontend = frontend.EventHandlingPandoraFrontend(conftest.config(), mock.Mock())
            self.frontend.set_click_time()
            self.frontend.check_doubleclicked(action='stop')
            time.sleep(float(self.frontend.double_click_interval + 0.1))

            assert mock_process_event.called

    def test_wait_for_track_change_aborts_stop_event_on_track_change(self):
        with mock.patch.object(EventHandlingPandoraFrontend, '_process_event', mock.Mock()) as mock_process_event:

            self.frontend = frontend.EventHandlingPandoraFrontend(conftest.config(), mock.Mock())
            self.frontend.set_click_time()
            self.frontend.check_doubleclicked(action='stop')
            self.frontend.track_changed_event.set()

            assert not mock_process_event.called


# Test private methods that are not available in the pykka actor.

def test_is_double_click():
    static_frontend = frontend.EventHandlingPandoraFrontend(conftest.config(), mock.Mock())
    static_frontend.set_click_time()
    assert static_frontend._is_double_click()

    time.sleep(float(static_frontend.double_click_interval) + 0.1)
    assert static_frontend._is_double_click() is False
