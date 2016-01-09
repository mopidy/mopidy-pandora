from __future__ import absolute_import, division, print_function, unicode_literals

import Queue

import time

import unittest

from mock import mock

from mopidy import core, listener, models

from mopidy.audio import PlaybackState
from mopidy.core import CoreListener

import pykka

from mopidy_pandora import frontend
from mopidy_pandora.frontend import EventHandlingPandoraFrontend, PandoraFrontend
from mopidy_pandora.listener import PandoraBackendListener

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


class TestFrontend(BaseTest):
    def setUp(self):  # noqa: N802
        super(TestFrontend, self).setUp()
        self.frontend = frontend.PandoraFrontend.start(conftest.config(), self.core).proxy()

    def tearDown(self):  # noqa: N802
        super(TestFrontend, self).tearDown()

    def test_add_track_starts_playback(self):
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED
        self.core.tracklist.clear().get()
        self.frontend.add_track(self.tl_tracks[0].track, auto_play=True).get()

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        assert self.core.playback.get_current_track().get() == self.tl_tracks[0].track

    def test_add_track_trims_tracklist(self):
        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)

        # Remove first track so we can add it again
        self.core.tracklist.remove({'tlid': [self.tl_tracks[0].tlid]}).get()

        self.frontend.add_track(self.tl_tracks[0].track).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 2
        assert tl_tracks[-1].track == self.tl_tracks[0].track

    def test_only_execute_for_pandora_executes_for_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert func_mock.called

    def test_next_track_available_adds_track_to_playlist(self):
        self.core.tracklist.clear().get()
        self.core.tracklist.add(uris=[self.tl_tracks[0].track.uri])
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        self.frontend.next_track_available(self.tl_tracks[1].track, True).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert tl_tracks[-1].track == self.tl_tracks[1].track
        assert self.core.playback.get_current_track().get() == self.tl_tracks[1].track

    def test_next_track_available_forces_stop_if_no_more_tracks(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert self.core.playback.get_state().get() == PlaybackState.PLAYING
        self.frontend.next_track_available(None).get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_only_execute_for_pandora_does_not_execute_for_non_pandora_uri(self):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = str('func_mock')
        func_mock.return_value = True

        self.core.playback.play(tlid=self.tl_tracks[3].tlid).get()
        frontend.only_execute_for_pandora_uris(func_mock)(self)

        assert not func_mock.called

    def test_options_changed_triggers_etup(self):
        with mock.patch.object(PandoraFrontend, 'set_options', mock.Mock()) as set_options_mock:
            self.frontend.setup_required = False
            listener.send(CoreListener, 'options_changed')
            self.replay_events(self.frontend)
            assert set_options_mock.called

    def test_set_options_performs_auto_setup(self):
        assert self.frontend.setup_required.get()
        self.core.tracklist.set_repeat(True).get()
        self.core.tracklist.set_consume(False).get()
        self.core.tracklist.set_random(True).get()
        self.core.tracklist.set_single(True).get()
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.replay_events(self.frontend)

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
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        assert self.core.playback.get_state().get() == PlaybackState.PLAYING

        self.frontend.skip_limit_exceeded().get()
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_station_change_does_not_trim_currently_playing_track_from_tracklist(self):
        with mock.patch.object(PandoraFrontend, 'is_station_changed', mock.Mock(return_value=True)):

            self.core.tracklist.clear().get()
            self.core.tracklist.add(uris=[self.tl_tracks[0].track.uri])
            self.frontend.changing_track(self.tl_tracks[0].track).get()
            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            assert len(tl_tracks) == 1
            assert tl_tracks[0].track == self.tl_tracks[0].track

    def test_is_end_of_tracklist_reached(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()

        assert not self.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_last_track(self):
        self.core.playback.play(tlid=self.tl_tracks[-1].tlid).get()

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

        # Check against track of a different station
        assert self.frontend.is_station_changed(self.tl_tracks[4].track).get()

    def test_is_station_changed_no_history(self):
        assert not self.frontend.is_station_changed(self.tl_tracks[0].track).get()

    def test_changing_track_no_op(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.next().get()  # Add track to history

        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
        self.replay_events(self.frontend)

        self.frontend.changing_track(self.tl_tracks[1].track).get()
        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)
        assert self.events.qsize() == 0

    def test_changing_track_station_changed(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.play(tlid=self.tl_tracks[4].tlid).get()
        self.replay_events(self.frontend)

        assert len(self.core.tracklist.get_tl_tracks().get()) == len(self.tl_tracks)

        self.frontend.changing_track(self.tl_tracks[4].track).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 1  # Tracks were trimmed from the tracklist
        assert tl_tracks[0] == self.tl_tracks[4]  # Only the track recently changed to is left in the tracklist

        is_event = []
        while True:
            try:
                e = self.events.get(timeout=0.1)
                is_event.append(e == ('end_of_tracklist_reached', {'station_id': 'id_mock_other',
                                                                   'auto_play': False}))
            except Queue.Empty:
                # All events processed.
                break
        assert any(is_event)

    def test_track_unplayable_removes_tracks_from_tracklist(self):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        unplayable_track = tl_tracks[0]
        self.frontend.track_unplayable(unplayable_track.track).get()

        self.assertEqual(unplayable_track in self.core.tracklist.get_tl_tracks().get(), False)

    def test_track_unplayable_triggers_end_of_tracklist_event(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.replay_events(self.frontend)

        self.frontend.track_unplayable(self.tl_tracks[-1].track).get()
        is_event = []
        while True:
            try:
                is_event.append(self.events.get(timeout=0.1)[0] == 'end_of_tracklist_reached')
            except Queue.Empty:
                # All events processed.
                break
        assert any(is_event)
        assert self.core.playback.get_state().get() == PlaybackState.STOPPED


class TestEventHandlingFrontend(BaseTest):
    def setUp(self):  # noqa: N802
        super(TestEventHandlingFrontend, self).setUp()
        self.frontend = frontend.EventHandlingPandoraFrontend.start(conftest.config(), self.core).proxy()
        self.core.tracklist.set_consume(True).get()  # Set consume mode so that tracklist behaves as expected.

    def tearDown(self):  # noqa: N802
        super(TestEventHandlingFrontend, self).tearDown()

    def test_delete_station_clears_tracklist_on_finish(self):
        assert len(self.core.tracklist.get_tl_tracks().get()) > 0

        listener.send(PandoraBackendListener, 'event_processed',
                      track_uri=self.tracks[0].uri,
                      pandora_event='delete_station')
        self.replay_events(self.frontend)

        assert len(self.core.tracklist.get_tl_tracks().get()) == 0

    def test_events_processed_on_resume_stop_and_change_track(self):
        with mock.patch.object(EventHandlingPandoraFrontend, 'process_event', mock.Mock()) as process_mock:

            # Pause -> Resume
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.core.playback.seek(100).get()
            self.core.playback.pause().get()
            self.core.playback.resume().get()
            self.replay_events(self.frontend)

            assert process_mock.called
            process_mock.reset_mock()
            self.events = Queue.Queue()

            # Pause -> Stop
            self.core.playback.pause().get()
            self.core.playback.stop().get()
            self.replay_events(self.frontend)
            time.sleep(self.frontend.double_click_interval.get() + 0.1)  # Wait for 'change_track' timeout

            assert process_mock.called
            process_mock.reset_mock()
            self.events = Queue.Queue()

            # Change track
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.core.playback.seek(100).get()
            self.core.playback.pause().get()
            self.core.playback.next().get()
            self.replay_events(self.frontend)

            self.frontend.changing_track(self.tl_tracks[1].track).get()
            # e = self.events.get(timeout=0.1)  # Wait for processing to finish

            assert process_mock.called
            process_mock.reset_mock()
            self.events = Queue.Queue()

    def test_get_event_targets_invalid_event_no_op(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.replay_events(self.frontend)

        self.frontend.process_event(event='invalid').get()
        assert self.events.qsize() == 0

    def test_get_event_targets_change_next(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.core.playback.next().get()
        self.replay_events(self.frontend)

        self.frontend.changing_track(track=self.tl_tracks[1].track).get()

        e = self.events.get(timeout=0.1)
        assert e[0] == 'event_triggered'
        assert e[1]['track_uri'] == self.tl_tracks[0].track.uri
        assert e[1]['pandora_event'] == self.frontend.settings.get()['change_track_next']

    def test_get_event_targets_change_previous(self):
        self.core.playback.play(tlid=self.tl_tracks[1].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.core.playback.previous().get()
        self.replay_events(self.frontend)

        self.frontend.changing_track(track=self.tl_tracks[0].track).get()

        e = self.events.get(timeout=0.1)
        assert e[0] == 'event_triggered'
        assert e[1]['track_uri'] == self.tl_tracks[1].track.uri
        assert e[1]['pandora_event'] == self.frontend.settings.get()['change_track_previous']

    def test_get_event_targets_resume(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.core.playback.resume().get()
        self.replay_events(self.frontend, until='track_playback_resumed')

        e = self.events.get(timeout=0.1)
        assert e[0] == 'event_triggered'
        assert e[1]['track_uri'] == self.tl_tracks[0].track.uri
        assert e[1]['pandora_event'] == self.frontend.settings.get()['resume']

    def test_pause_starts_double_click_timer(self):
        assert self.frontend.get_click_marker().get().time == 0
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.replay_events(self.frontend)

        assert self.frontend.get_click_marker().get().time > 0

    def test_pause_does_not_start_timer_at_track_start(self):
        assert self.frontend.get_click_marker().get().time == 0
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.pause().get()
        self.replay_events(self.frontend)

        self.frontend.track_playback_paused(mock.Mock(), 0).get()
        assert self.frontend.get_click_marker().get().time == 0

    def test_process_event_handles_exception(self):
        with mock.patch.object(frontend.EventHandlingPandoraFrontend, '_get_event_targets',
                               mock.PropertyMock(return_value=None, side_effect=KeyError('error_mock'))):
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.core.playback.seek(100).get()
            self.core.playback.pause().get()
            self.replay_events(self.frontend)

            self.core.playback.resume().get()
            self.replay_events(self.frontend, until='track_playback_resumed')

            assert self.events.qsize() == 0  # Check that no events were triggered

    def test_process_event_ignores_ads(self):
        self.core.playback.play(tlid=self.tl_tracks[2].tlid).get()
        self.core.playback.seek(100)
        self.core.playback.pause().get()
        self.replay_events(self.frontend)

        self.core.playback.resume().get()
        self.replay_events(self.frontend, until='track_playback_resumed')

        assert self.events.qsize() == 0  # Check that no events were triggered

    def test_process_event_resumes_playback_for_change_track(self):
        actions = ['stop', 'change_track', 'resume']

        for action in actions:
            self.events = Queue.Queue()  # Make sure that the queue is empty
            self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
            self.core.playback.seek(100)
            self.core.playback.pause().get()
            self.replay_events(self.frontend)
            assert self.core.playback.get_state().get() == PlaybackState.PAUSED

            if action == 'change_track':
                self.core.playback.next().get()
                self.frontend.process_event(event=action).get()

                self.assertEqual(self.core.playback.get_state().get(),
                                 PlaybackState.PLAYING,
                                 "Failed to set playback for action '{}'".format(action))
            else:
                self.frontend.process_event(event=action).get()
                self.assertEqual(self.core.playback.get_state().get(),
                                 PlaybackState.PAUSED,
                                 "Failed to set playback for action '{}'".format(action))

    def test_process_event_triggers_event(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.replay_events(self.frontend)
        self.core.playback.resume().get()
        self.replay_events(self.frontend, until='track_playback_resumed')

        e = self.events.get(timeout=0.1)
        assert e[0] == 'event_triggered'
        assert e[1]['track_uri'] == self.tl_tracks[0].track.uri
        assert e[1]['pandora_event'] == 'thumbs_up'
        assert self.events.qsize() == 0

    def test_playback_state_changed_handles_stop(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.core.playback.stop().get()
        self.replay_events(self.frontend)

        time.sleep(float(self.frontend.double_click_interval.get() + 0.1))
        e = self.events.get(timeout=0.1)  # Wait for processing to finish
        assert e[0] == 'event_triggered'

    def test_playback_state_changed_handles_change_track(self):
        self.core.playback.play(tlid=self.tl_tracks[0].tlid).get()
        self.core.playback.seek(100).get()
        self.core.playback.pause().get()
        self.core.playback.next().get()
        self.replay_events(self.frontend)

        self.frontend.changing_track(self.tl_tracks[1].track).get()
        e = self.events.get(timeout=0.1)  # Wait for processing to finish
        assert e[0] == 'event_triggered'


# Test private methods that are not available in the pykka actor.

def test_is_double_click():
    static_frontend = frontend.EventHandlingPandoraFrontend(conftest.config(), mock.Mock())
    track_mock = mock.Mock(spec=models.Track)
    track_mock.uri = 'pandora:track:id_mock:token_mock'
    tl_track_mock = mock.Mock(spec=models.TlTrack)
    tl_track_mock.track = track_mock

    static_frontend.set_click_marker(tl_track_mock)
    assert static_frontend._is_double_click()

    static_frontend.set_click_marker(tl_track_mock)
    time.sleep(float(static_frontend.double_click_interval) + 0.5)
    assert static_frontend._is_double_click() is False
