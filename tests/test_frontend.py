import time
from unittest import mock

from mopidy import listener, models
from mopidy.audio import PlaybackState
from mopidy.core import CoreListener
from mopidy_pandora import frontend
from mopidy_pandora.frontend import EventMarker, MatchResult, PandoraFrontend
from mopidy_pandora.listener import (
    EventMonitorListener,
    PandoraBackendListener,
    PandoraFrontendListener,
)

from tests import conftest


class TestPandoraFrontend:
    def test_add_track_starts_playback(self, mopidy):
        assert mopidy.core.playback.get_state().get() == PlaybackState.STOPPED
        mopidy.core.tracklist.clear()
        mopidy.frontend.add_track(
            mopidy.tl_tracks[0].track, auto_play=True
        ).get()
        mopidy.replay_events()

        assert mopidy.core.playback.get_state().get() == PlaybackState.PLAYING
        assert (
            mopidy.core.playback.get_current_track().get()
            == mopidy.tl_tracks[0].track
        )

    def test_add_track_trims_tracklist(self, mopidy):
        assert len(mopidy.core.tracklist.get_tl_tracks().get()) == len(
            mopidy.tl_tracks
        )

        # Remove first track so we can add it again
        mopidy.core.tracklist.remove({"tlid": [mopidy.tl_tracks[0].tlid]})

        mopidy.frontend.add_track(mopidy.tl_tracks[0].track).get()
        tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
        assert len(tl_tracks) == 2
        assert tl_tracks[-1].track == mopidy.tl_tracks[0].track

    def test_next_track_available_adds_track_to_playlist(self, mopidy):
        mopidy.core.tracklist.clear()
        mopidy.core.tracklist.add(uris=[mopidy.tl_tracks[0].track.uri])
        tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
        mopidy.core.playback.play(tlid=tl_tracks[0].tlid)
        mopidy.replay_events(until="track_playback_started")

        mopidy.frontend.next_track_available(
            mopidy.tl_tracks[1].track, True
        ).get()
        tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
        mopidy.replay_events()

        assert tl_tracks[-1].track == mopidy.tl_tracks[1].track
        assert (
            mopidy.core.playback.get_current_track().get()
            == mopidy.tl_tracks[1].track
        )

    def test_next_track_available_forces_stop_if_no_more_tracks(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
        mopidy.replay_events()

        assert mopidy.core.playback.get_state().get() == PlaybackState.PLAYING
        mopidy.frontend.next_track_available(None).get()
        assert mopidy.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_only_execute_for_pandora_does_not_execute_for_non_pandora_uri(
        self, mopidy
    ):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = "func_mock"
        func_mock.return_value = True

        mopidy.core.playback.play(tlid=mopidy.tl_tracks[3].tlid)
        frontend.only_execute_for_pandora_uris(func_mock)(mopidy)

        assert not func_mock.called

    def test_only_execute_for_pandora_does_not_execute_for_malformed_pandora_uri(
        self, mopidy
    ):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = "func_mock"
        func_mock.return_value = True

        tl_track_mock = mock.Mock(spec=models.TlTrack)
        track_mock = mock.Mock(spec=models.Track)
        track_mock.uri = "pandora:invalid_uri"
        tl_track_mock.track = track_mock
        frontend.only_execute_for_pandora_uris(func_mock)(
            mopidy, tl_track=tl_track_mock
        )

        assert not func_mock.called

    def test_only_execute_for_pandora_executes_for_pandora_uri(self, mopidy):
        func_mock = mock.PropertyMock()
        func_mock.__name__ = "func_mock"
        func_mock.return_value = True

        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid).get()
        mopidy.replay_events()
        frontend.only_execute_for_pandora_uris(func_mock)(mopidy)

        assert func_mock.called

    def test_options_changed_triggers_setup(self, mopidy):
        with mock.patch.object(
            PandoraFrontend, "set_options", mock.Mock()
        ) as set_options_mock:
            mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid).get()
            mopidy.frontend.setup_required = False
            listener.send(CoreListener, "options_changed")
            mopidy.replay_events()
            assert set_options_mock.called

    def test_set_options_performs_auto_setup(self, mopidy):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            assert mopidy.frontend.setup_required.get()
            mopidy.core.tracklist.set_repeat(True)
            mopidy.core.tracklist.set_consume(False)
            mopidy.core.tracklist.set_random(True)
            mopidy.core.tracklist.set_single(True)
            mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid).get()
            mopidy.replay_events()

            thread_joiner.wait(timeout=1.0)

            assert mopidy.core.tracklist.get_repeat().get() is False
            assert mopidy.core.tracklist.get_consume().get() is True
            assert mopidy.core.tracklist.get_random().get() is False
            assert mopidy.core.tracklist.get_single().get() is False
            mopidy.replay_events()

            assert not mopidy.frontend.setup_required.get()

    def test_set_options_skips_auto_setup_if_not_configured(
        self, config, mopidy
    ):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)

        config["pandora"]["auto_setup"] = False
        mopidy.frontend.setup_required = True

        mopidy.replay_events()
        assert mopidy.frontend.setup_required

    def test_set_options_triggered_on_core_events(self, mopidy):
        with mock.patch.object(
            PandoraFrontend, "set_options", mock.Mock()
        ) as set_options_mock:
            tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
            core_events = {
                "track_playback_started": {"tl_track": tl_tracks[0]},
                "track_playback_ended": {
                    "tl_track": tl_tracks[0],
                    "time_position": 100,
                },
                "track_playback_paused": {
                    "tl_track": tl_tracks[0],
                    "time_position": 100,
                },
                "track_playback_resumed": {
                    "tl_track": tl_tracks[0],
                    "time_position": 100,
                },
            }

            mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)

            for (event, kwargs) in core_events.items():
                mopidy.frontend.setup_required = True
                listener.send(CoreListener, event, **kwargs)
                mopidy.replay_events()
                assert set_options_mock.called is True
                set_options_mock.reset_mock()

    def test_skip_limit_exceed_stops_playback(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
        mopidy.replay_events()
        assert mopidy.core.playback.get_state().get() == PlaybackState.PLAYING

        mopidy.frontend.skip_limit_exceeded().get()
        assert mopidy.core.playback.get_state().get() == PlaybackState.STOPPED

    def test_station_change_does_not_trim_currently_playing_track_from_tracklist(
        self, mopidy
    ):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            with mock.patch.object(
                PandoraFrontend,
                "is_station_changed",
                mock.Mock(return_value=True),
            ):
                mopidy.core.playback.play(tlid=mopidy.tl_tracks[4].tlid)
                mopidy.replay_events()

                thread_joiner.wait(
                    timeout=1.0
                )  # Wait until threads spawned by frontend have finished.

                tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
                assert len(tl_tracks) == 1
                assert tl_tracks[0].track == mopidy.tl_tracks[4].track

    def test_get_active_uri_order_of_precedence(self, mopidy):
        # Should be 'track' -> 'tl_track' -> 'current_tl_track' -> 'history[0]'
        kwargs = {}
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
        mopidy.replay_events()
        assert (
            frontend.get_active_uri(mopidy.core, **kwargs)
            == mopidy.tl_tracks[0].track.uri
        )

        # No easy way to test retrieving from history as it is not possible to
        # set core.playback_current_tl_track to None

        # mopidy.core.playback.next()
        # mopidy.core.playback.stop()
        # mopidy.replay_events()
        # assert (
        #     frontend.get_active_uri(mopidy.core, **kwargs) ==
        #     mopidy.tl_tracks[1].track.uri
        # )

        kwargs["tl_track"] = mopidy.tl_tracks[2]
        assert (
            frontend.get_active_uri(mopidy.core, **kwargs)
            == mopidy.tl_tracks[2].track.uri
        )

        kwargs = {"track": mopidy.tl_tracks[3].track}
        assert (
            frontend.get_active_uri(mopidy.core, **kwargs)
            == mopidy.tl_tracks[3].track.uri
        )

    def test_is_end_of_tracklist_reached(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)

        assert not mopidy.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_last_track(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[-1].tlid)
        mopidy.replay_events()

        assert mopidy.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_no_tracks(self, mopidy):
        mopidy.core.tracklist.clear()

        assert mopidy.frontend.is_end_of_tracklist_reached().get()

    def test_is_end_of_tracklist_reached_second_last_track(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[3].tlid)

        assert not mopidy.frontend.is_end_of_tracklist_reached(
            mopidy.tl_tracks[3].track
        ).get()

    def test_is_station_changed(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
        mopidy.replay_events()
        mopidy.core.playback.next()
        mopidy.replay_events()

        # Check against track of a different station
        assert mopidy.frontend.is_station_changed(
            mopidy.tl_tracks[4].track
        ).get()

    def test_is_station_changed_no_history(self, mopidy):
        assert not mopidy.frontend.is_station_changed(
            mopidy.tl_tracks[0].track
        ).get()

    def test_changing_track_no_op(self, mopidy):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
            mopidy.core.playback.next()

            assert len(mopidy.core.tracklist.get_tl_tracks().get()) == len(
                mopidy.tl_tracks
            )
            mopidy.replay_events()

            thread_joiner.wait(
                timeout=1.0
            )  # Wait until threads spawned by frontend have finished.

            assert len(mopidy.core.tracklist.get_tl_tracks().get()) == len(
                mopidy.tl_tracks
            )
            assert mopidy.events.qsize() == 0

    def test_changing_track_station_changed(self, mopidy):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            mopidy.core.tracklist.clear()
            mopidy.core.tracklist.add(
                uris=[
                    mopidy.tl_tracks[0].track.uri,
                    mopidy.tl_tracks[4].track.uri,
                ]
            )
            tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
            assert len(tl_tracks) == 2

            mopidy.core.playback.play(tlid=tl_tracks[0].tlid)
            mopidy.replay_events()
            mopidy.core.playback.seek(100)
            mopidy.replay_events()
            mopidy.core.playback.next()

            mopidy.replay_events(until="end_of_tracklist_reached")

            thread_joiner.wait(
                timeout=1.0
            )  # Wait until threads spawned by frontend have finished.

            tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
            assert len(tl_tracks) == 1  # Tracks were trimmed from the tracklist
            # Only the track recently changed to is left in the tracklist
            assert tl_tracks[0].track.uri == mopidy.tl_tracks[4].track.uri

            call = mock.call(
                PandoraFrontendListener,
                "end_of_tracklist_reached",
                station_id="id_mock_other",
                auto_play=False,
            )

            assert call in mopidy.send_mock.mock_calls

    def test_track_unplayable_removes_tracks_from_tracklist(self, mopidy):
        tl_tracks = mopidy.core.tracklist.get_tl_tracks().get()
        unplayable_track = tl_tracks[0]
        mopidy.frontend.track_unplayable(unplayable_track.track).get()

        assert (
            unplayable_track not in mopidy.core.tracklist.get_tl_tracks().get()
        )

    def test_track_unplayable_triggers_end_of_tracklist_event(self, mopidy):
        mopidy.core.playback.play(tlid=mopidy.tl_tracks[0].tlid)
        mopidy.replay_events()

        mopidy.frontend.track_unplayable(mopidy.tl_tracks[-1].track).get()

        call = mock.call(
            PandoraFrontendListener,
            "end_of_tracklist_reached",
            station_id="id_mock",
            auto_play=True,
        )

        assert call in mopidy.send_mock.mock_calls

        assert mopidy.core.playback.get_state().get() == PlaybackState.STOPPED


class TestEventMonitorFrontend:
    def test_delete_station_clears_tracklist_on_finish(
        self, mopidy_with_monitor
    ):
        mopidy_with_monitor.core.playback.play(
            tlid=mopidy_with_monitor.tl_tracks[0].tlid
        )
        mopidy_with_monitor.replay_events()
        assert len(mopidy_with_monitor.core.tracklist.get_tl_tracks().get()) > 0

        listener.send(
            PandoraBackendListener,
            "event_processed",
            track_uri=mopidy_with_monitor.tracks[0].uri,
            pandora_event="delete_station",
        )
        mopidy_with_monitor.replay_events()

        assert (
            len(mopidy_with_monitor.core.tracklist.get_tl_tracks().get()) == 0
        )

    def test_detect_track_change_next(self, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            ).get()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100).get()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.next().get()
            mopidy_with_monitor.replay_events()

            thread_joiner.wait(timeout=1.0)

            mopidy_with_monitor.replay_events()
            call = mock.call(
                EventMonitorListener,
                "track_changed_next",
                old_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                new_uri=mopidy_with_monitor.tl_tracks[1].track.uri,
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_detect_track_change_next_from_paused(self, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=5.0) as thread_joiner:
            # Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.next().get()
            mopidy_with_monitor.replay_events(until="track_changed_next")

            thread_joiner.wait(timeout=5.0)
            call = mock.call(
                EventMonitorListener,
                "track_changed_next",
                old_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                new_uri=mopidy_with_monitor.tl_tracks[1].track.uri,
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_detect_track_change_no_op(self, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.stop()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            ).get()
            mopidy_with_monitor.replay_events(until="track_playback_started")

            thread_joiner.wait(timeout=1.0)
            assert mopidy_with_monitor.events.empty()

    def test_detect_track_change_previous(self, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.previous().get()
            mopidy_with_monitor.replay_events(until="track_changed_previous")

            thread_joiner.wait(timeout=1.0)
            call = mock.call(
                EventMonitorListener,
                "track_changed_previous",
                old_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                new_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_detect_track_change_previous_from_paused(
        self, mopidy_with_monitor
    ):
        with conftest.ThreadJoiner(timeout=5.0) as thread_joiner:
            # Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.previous().get()
            mopidy_with_monitor.replay_events(until="track_changed_previous")

            thread_joiner.wait(timeout=5.0)
            call = mock.call(
                EventMonitorListener,
                "track_changed_previous",
                old_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                new_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_events_triggered_on_next_action(self, config, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=5.0) as thread_joiner:
            # Pause -> Next
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.next().get()
            mopidy_with_monitor.replay_events(until="event_triggered")

            thread_joiner.wait(timeout=5.0)
            call = mock.call(
                EventMonitorListener,
                "event_triggered",
                track_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                pandora_event=config["pandora"]["on_pause_next_click"],
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_events_triggered_on_previous_action(
        self, config, mopidy_with_monitor
    ):
        with conftest.ThreadJoiner(timeout=5.0) as thread_joiner:
            # Pause -> Previous
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            ).get()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100).get()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause().get()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.previous().get()
            mopidy_with_monitor.replay_events(until="event_triggered")

            thread_joiner.wait(timeout=5.0)
            call = mock.call(
                EventMonitorListener,
                "event_triggered",
                track_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                pandora_event=config["pandora"]["on_pause_previous_click"],
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_events_triggered_on_resume_action(
        self, config, mopidy_with_monitor
    ):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.resume().get()
            mopidy_with_monitor.replay_events(until="event_triggered")

            thread_joiner.wait(timeout=1.0)
            call = mock.call(
                EventMonitorListener,
                "event_triggered",
                track_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                pandora_event=config["pandora"]["on_pause_resume_click"],
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_events_triggered_on_triple_click_action(
        self, config, mopidy_with_monitor
    ):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            # Pause -> Resume -> Pause
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.resume()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause().get()
            mopidy_with_monitor.replay_events(until="event_triggered")

            thread_joiner.wait(timeout=1.0)
            call = mock.call(
                EventMonitorListener,
                "event_triggered",
                track_uri=mopidy_with_monitor.tl_tracks[0].track.uri,
                pandora_event=config["pandora"]["on_pause_resume_pause_click"],
            )

            assert call in mopidy_with_monitor.send_mock.mock_calls

    def test_monitor_ignores_ads(self, mopidy_with_monitor):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[2].tlid
            )
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.resume().get()
            mopidy_with_monitor.replay_events(until="track_playback_resumed")

            thread_joiner.wait(timeout=1.0)
            assert (
                mopidy_with_monitor.events.qsize() == 0
            )  # Check that no events were triggered

    def test_monitor_resumes_playback_after_event_trigger(
        self, mopidy_with_monitor
    ):
        with conftest.ThreadJoiner(timeout=1.0) as thread_joiner:
            mopidy_with_monitor.core.playback.play(
                tlid=mopidy_with_monitor.tl_tracks[0].tlid
            )
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.seek(100)
            mopidy_with_monitor.replay_events()
            mopidy_with_monitor.core.playback.pause()
            mopidy_with_monitor.replay_events()
            assert (
                mopidy_with_monitor.core.playback.get_state().get()
                == PlaybackState.PAUSED
            )

            mopidy_with_monitor.core.playback.next().get()
            mopidy_with_monitor.replay_events()

            thread_joiner.wait(timeout=5.0)
            assert (
                mopidy_with_monitor.core.playback.get_state().get()
                == PlaybackState.PLAYING
            )


class TestEventSequence:
    def test_events_ignored_if_time_position_is_zero(
        self, event_sequences, tl_track_mock
    ):
        for es in event_sequences:
            es.notify("e1", tl_track=tl_track_mock)
        for es in event_sequences:
            assert not es.is_monitoring()

    def test_start_monitor_on_event(self, event_sequences, tl_track_mock):
        for es in event_sequences:
            es.notify("e1", tl_track=tl_track_mock, time_position=100)
        for es in event_sequences:
            assert es.is_monitoring()

    def test_start_monitor_handles_no_tl_track(
        self, event_sequences, tl_track_mock
    ):
        for es in event_sequences:
            es.notify("e1", tl_track=tl_track_mock, time_position=100)
        for es in event_sequences:
            assert es.is_monitoring()

    def test_stop_monitor_adds_result_to_queue(
        self, event_sequences, tl_track_mock, rq
    ):
        for es in event_sequences[0:2]:
            es.notify("e1", tl_track=tl_track_mock, time_position=100)
            es.notify("e2", time_position=100)
            es.notify("e3", time_position=100)

        for es in event_sequences[0:2]:
            es.wait(1.0)
            assert not es.is_monitoring()

        assert rq.qsize() == 2

    def test_stop_monitor_only_waits_for_matched_events(
        self, event_sequence_wait, rq
    ):
        event_sequence_wait.notify("e1", time_position=100)
        event_sequence_wait.notify(
            "e_not_in_monitored_sequence", time_position=100
        )

        time.sleep(0.1 * 1.1)
        assert not event_sequence_wait.is_monitoring()
        assert rq.qsize() == 0

    def test_stop_monitor_waits_for_event(self, event_sequence_wait, rq):
        event_sequence_wait.notify("e1", time_position=100)
        event_sequence_wait.notify("e2", time_position=100)
        event_sequence_wait.notify("e3", time_position=100)

        assert event_sequence_wait.is_monitoring()
        assert rq.qsize() == 0

        event_sequence_wait.notify("w1", time_position=100)
        event_sequence_wait.wait(timeout=1.0)

        assert not event_sequence_wait.is_monitoring()
        assert rq.qsize() == 1

    def test_get_stop_monitor_ensures_that_all_events_occurred(
        self, event_sequence, rq, tl_track_mock
    ):
        event_sequence.notify("e1", tl_track=tl_track_mock, time_position=100)
        event_sequence.notify("e2", time_position=100)
        event_sequence.notify("e3", time_position=100)
        assert rq.qsize() == 0

        event_sequence.wait(timeout=1.0)
        event_sequence.events_seen = ["e1", "e2", "e3"]
        assert rq.qsize() > 0

    def test_get_stop_monitor_strict_ensures_that_events_were_seen_in_order(
        self, event_sequence_strict, tl_track_mock, rq
    ):
        event_sequence_strict.notify(
            "e1", tl_track=tl_track_mock, time_position=100
        )
        event_sequence_strict.notify("e3", time_position=100)
        event_sequence_strict.notify("e2", time_position=100)
        event_sequence_strict.wait(timeout=1.0)
        assert rq.qsize() == 0

        event_sequence_strict.notify(
            "e1", tl_track=tl_track_mock, time_position=100
        )
        event_sequence_strict.notify("e2", time_position=100)
        event_sequence_strict.notify("e3", time_position=100)
        event_sequence_strict.wait(timeout=1.0)
        assert rq.qsize() > 0

    def test_get_ratio_handles_repeating_events(self, event_sequence):
        event_sequence.target_sequence = ["e1", "e2", "e3", "e1"]
        event_sequence.events_seen = ["e1", "e2", "e3", "e1"]
        assert event_sequence.get_ratio() > 0

    def test_get_ratio_enforces_strict_matching(self, event_sequence_strict):
        event_sequence_strict.events_seen = ["e1", "e2", "e3", "e4"]
        assert event_sequence_strict.get_ratio() == 0

        event_sequence_strict.events_seen = ["e1", "e2", "e3"]
        assert event_sequence_strict.get_ratio() == 1


class TestMatchResult:
    def test_match_result_comparison(self):
        mr1 = MatchResult(EventMarker("e1", "u1", 0), 1)
        mr2 = MatchResult(EventMarker("e1", "u1", 0), 2)

        assert mr1 < mr2
        assert mr2 > mr1
        assert mr1 != mr2

        mr2.ratio = 1
        assert mr1 == mr2
