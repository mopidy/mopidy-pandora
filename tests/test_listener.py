from unittest import mock

from mopidy import models


class TestEventMonitorListener:
    def test_on_event_forwards_to_specific_handler(
        self, event_monitor_listener
    ):
        event_monitor_listener.event_triggered = mock.Mock()

        event_monitor_listener.on_event(
            "event_triggered",
            track_uri="pandora:track:id_mock:token_mock",
            pandora_event="event_mock",
        )

        event_monitor_listener.event_triggered.assert_called_with(
            track_uri="pandora:track:id_mock:token_mock",
            pandora_event="event_mock",
        )

    def test_listener_has_default_impl_for_event_triggered(
        self, event_monitor_listener
    ):
        event_monitor_listener.event_triggered(
            "pandora:track:id_mock:token_mock", "event_mock"
        )

    def test_listener_has_default_impl_for_track_changed_previous(
        self, event_monitor_listener
    ):
        event_monitor_listener.track_changed_previous(
            old_uri="pandora:track:id_mock:token_mock2",
            new_uri="pandora:track:id_mock:token_mock1",
        )

    def test_listener_has_default_impl_for_track_changed_next(
        self, event_monitor_listener
    ):
        event_monitor_listener.track_changed_next(
            old_uri="pandora:track:id_mock:token_mock1",
            new_uri="pandora:track:id_mock:token_mock2",
        )


class TestPandoraFrontendListener:
    def test_on_event_forwards_to_specific_handler(self, frontend_listener):
        frontend_listener.end_of_tracklist_reached = mock.Mock()

        frontend_listener.on_event(
            "end_of_tracklist_reached", station_id="id_mock", auto_play=False
        )

        frontend_listener.end_of_tracklist_reached.assert_called_with(
            station_id="id_mock", auto_play=False
        )

    def test_listener_has_default_impl_for_end_of_tracklist_reached(
        self, frontend_listener
    ):
        frontend_listener.end_of_tracklist_reached(
            station_id="id_mock", auto_play=False
        )


class TestPandoraBackendListener:
    def test_on_event_forwards_to_specific_handler(self, backend_listener):
        backend_listener.next_track_available = mock.Mock()

        backend_listener.on_event(
            "next_track_available",
            track=models.Ref(name="name_mock"),
            auto_play=False,
        )

        backend_listener.next_track_available.assert_called_with(
            track=models.Ref(name="name_mock"), auto_play=False
        )

    def test_listener_has_default_impl_for_next_track_available(
        self, backend_listener
    ):
        backend_listener.next_track_available(
            track=models.Ref(name="name_mock"), auto_play=False
        )

    def test_listener_has_default_impl_for_event_processed(
        self, backend_listener
    ):
        backend_listener.event_processed(
            track_uri="pandora:track:id_mock:token_mock",
            pandora_event="event_mock",
        )


class TestPandoraPlaybackListener:
    def test_on_event_forwards_to_specific_handler(self, playback_listener):
        playback_listener.track_changing = mock.Mock()

        playback_listener.on_event(
            "track_changing", track=models.Ref(name="name_mock")
        )

        playback_listener.track_changing.assert_called_with(
            track=models.Ref(name="name_mock")
        )

    def test_listener_has_default_impl_for_track_changing(
        self, playback_listener
    ):
        playback_listener.track_changing(track=models.Ref(name="name_mock"))

    def test_listener_has_default_impl_for_track_unplayable(
        self, playback_listener
    ):
        playback_listener.track_unplayable(track=models.Ref(name="name_mock"))

    def test_listener_has_default_impl_for_skip_limit_exceeded(
        self, playback_listener
    ):
        playback_listener.skip_limit_exceeded()
