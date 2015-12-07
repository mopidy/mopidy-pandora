from __future__ import unicode_literals

import threading
import time

import conftest

import mock

from mopidy import audio, backend as backend_api, models

from pandora.errors import PandoraException

from pandora.models.pandora import PlaylistItem, Station

import pytest

from mopidy_pandora import playback

from mopidy_pandora.backend import MopidyPandoraAPIClient

from mopidy_pandora.playback import PandoraPlaybackProvider
from mopidy_pandora.rpc import RPCClient

from mopidy_pandora.uri import TrackUri


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def provider(audio_mock, config):
    if config['pandora']['event_support_enabled']:
        return playback.EventSupportPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))
    else:
        return playback.PandoraPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_change_track_aborts_if_no_track_uri(provider):
    track = models.Track(uri=None)

    assert provider.change_track(track) is False


def test_pause_starts_double_click_timer(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):
        assert provider.backend.supports_events
        assert provider._double_click_handler.get_click_time() == 0
        provider.pause()
        assert provider._double_click_handler.get_click_time() > 0


def test_pause_does_not_start_timer_at_track_start(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=0):
        assert provider.backend.supports_events
        assert provider._double_click_handler.get_click_time() == 0
        provider.pause()
        assert provider._double_click_handler.get_click_time() == 0


def test_resume_checks_for_double_click(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):
        assert provider.backend.supports_events
        is_double_click_mock = mock.PropertyMock()
        process_click_mock = mock.PropertyMock()
        provider._double_click_handler.is_double_click = is_double_click_mock
        provider._double_click_handler.process_click = process_click_mock
        provider.resume()

        provider._double_click_handler.is_double_click.assert_called_once_with()


def test_resume_double_click_call(config, provider):
    assert provider.backend.supports_events

    process_click_mock = mock.PropertyMock()

    provider._double_click_handler.process_click = process_click_mock
    provider._double_click_handler.set_click_time()
    provider.resume()

    provider._double_click_handler.process_click.assert_called_once_with(config['pandora']['on_pause_resume_click'],
                                                                         provider.active_track_uri)


def test_change_track_checks_for_double_click(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):
        with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):
            assert provider.backend.supports_events
            is_double_click_mock = mock.PropertyMock()
            process_click_mock = mock.PropertyMock()
            provider._double_click_handler.is_double_click = is_double_click_mock
            provider._double_click_handler.process_click = process_click_mock
            provider.backend.rpc_client.resume_playback = mock.PropertyMock()
            provider.change_track(models.Track(uri=TrackUri.from_track(conftest.playlist_item_mock()).uri))

            provider._double_click_handler.is_double_click.assert_called_once_with()


def test_change_track_double_click_call(config, provider, playlist_item_mock):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):
        assert provider.backend.supports_events

        track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
        track_1 = TrackUri.from_track(playlist_item_mock, 1).uri
        # track_2 = TrackUri.from_track(playlist_item_mock, 2).uri

        process_click_mock = mock.PropertyMock()

        provider._double_click_handler.process_click = process_click_mock
        provider.backend.rpc_client.resume_playback = mock.PropertyMock()
        provider._double_click_handler.set_click_time()
        provider.active_track_uri = track_0
        provider.change_track(models.Track(uri=track_1))

        provider._double_click_handler.process_click.assert_called_once_with(config['pandora']['on_pause_next_click'],
                                                                             provider.active_track_uri)

        provider._double_click_handler.set_click_time()

        provider.active_track_uri = track_1
        provider.change_track(models.Track(uri=track_0))

        provider._double_click_handler.process_click.assert_called_with(config['pandora']['on_pause_previous_click'],
                                                                        provider.active_track_uri)


def test_change_track(audio_mock, provider):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=True):
                track = models.Track(uri=TrackUri.from_track(conftest.playlist_item_mock()).uri)

                assert provider.change_track(track) is True
                assert audio_mock.prepare_change.call_count == 0
                assert audio_mock.start_playback.call_count == 0
                audio_mock.set_uri.assert_called_once_with(PlaylistItem.get_audio_url(
                    conftest.playlist_result_mock()["result"]["items"][0],
                    conftest.MOCK_DEFAULT_AUDIO_QUALITY))


def test_change_track_enforces_skip_limit(provider):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=False):
                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert PlaylistItem.get_is_playable.call_count == PandoraPlaybackProvider.SKIP_LIMIT


def test_change_track_handles_request_exceptions(config, caplog):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.request_exception_mock):
            track = models.Track(uri="pandora:track:test::::")

            playback = conftest.get_backend(config).playback

            assert playback.change_track(track) is False
            assert 'Error changing track' in caplog.text()


def test_change_track_resumes_playback(provider, playlist_item_mock):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):
        with mock.patch.object(RPCClient, 'resume_playback') as mock_rpc:
            assert provider.backend.supports_events

            event = threading.Event()

            def set_event():
                event.set()

            mock_rpc.side_effect = set_event

            track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
            track_1 = TrackUri.from_track(playlist_item_mock, 1).uri

            process_click_mock = mock.PropertyMock()

            provider._double_click_handler.process_click = process_click_mock
            provider._double_click_handler.set_click_time()
            provider.active_track_uri = track_0

            provider.change_track(models.Track(uri=track_1))

        if event.wait(timeout=1.0):
            mock_rpc.assert_called_once_with()
        else:
            assert False


def test_change_track_does_not_resume_playback_if_not_doubleclick(config, provider, playlist_item_mock):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):
        with mock.patch.object(RPCClient, 'resume_playback') as mock_rpc:
            assert provider.backend.supports_events

            event = threading.Event()

            def set_event():
                event.set()

            mock_rpc.side_effect = set_event

            track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
            track_1 = TrackUri.from_track(playlist_item_mock, 1).uri

            process_click_mock = mock.PropertyMock()

            click_interval = float(config['pandora']['double_click_interval']) + 1.0

            provider._double_click_handler.process_click = process_click_mock
            provider._double_click_handler.set_click_time(time.time() - click_interval)
            provider.active_track_uri = track_0
            provider.change_track(models.Track(uri=track_1))

        if event.wait(timeout=1.0):
            assert False
        else:
            assert not mock_rpc.called


def test_change_track_does_not_resume_playback_if_event_failed(provider, playlist_item_mock):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):
        with mock.patch.object(RPCClient, 'resume_playback') as mock_rpc:
            assert provider.backend.supports_events

            event = threading.Event()

            def set_event():
                event.set()

            mock_rpc.side_effect = set_event

            track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
            track_1 = TrackUri.from_track(playlist_item_mock, 1).uri

            e = PandoraException().from_code(0000, "Mock exception")
            provider._double_click_handler.thumbs_down = mock.Mock()
            provider._double_click_handler.thumbs_down.side_effect = e

            provider._double_click_handler.set_click_time()
            provider.active_track_uri = track_0
            provider.change_track(models.Track(uri=track_1))

        if event.wait(timeout=1.0):
            assert False
        else:
            assert not mock_rpc.called


def test_is_playable_handles_request_exceptions(provider, caplog):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', conftest.request_exception_mock):
                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert 'Error checking if track is playable' in caplog.text()


def test_translate_uri_returns_audio_url(provider):
    assert provider.translate_uri("pandora:track:test:::::audio_url") == "audio_url"


def test_auto_setup_only_called_once(provider):
    with mock.patch.multiple('mopidy_pandora.rpc.RPCClient', set_repeat=mock.DEFAULT, set_random=mock.DEFAULT,
                             set_consume=mock.DEFAULT, set_single=mock.DEFAULT) as values:
        with mock.patch.object(RPCClient, 'get_current_track_uri', return_value="pandora::::::"):

            event = threading.Event()

            def set_event(*args, **kwargs):
                event.set()

            values['set_single'].side_effect = set_event

            provider.prepare_change()

            if event.wait(timeout=1.0):
                values['set_repeat'].assert_called_once_with()
                values['set_random'].assert_called_once_with(False)
                values['set_consume'].assert_called_once_with(False)
                values['set_single'].assert_called_once_with(False)
            else:
                assert False

            event = threading.Event()
            values['set_single'].side_effect = set_event

            provider.prepare_change()

            if event.wait(timeout=1.0):
                assert False
            else:
                values['set_repeat'].assert_called_once_with()
                values['set_random'].assert_called_once_with(False)
                values['set_consume'].assert_called_once_with(False)
                values['set_single'].assert_called_once_with(False)
