from __future__ import unicode_literals

import conftest

import mock

from mopidy import audio, backend as backend_api, models

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

    assert provider.backend.supports_events
    assert provider._double_click_handler.click_time == 0
    provider.pause()
    assert provider._double_click_handler.click_time > 0


def test_resume_checks_for_double_click(provider):

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
    provider._double_click_handler.set_click()
    provider.resume()

    provider._double_click_handler.process_click.assert_called_once_with(config['pandora']['on_pause_resume_click'],
                                                                         provider.active_track_uri)


def test_change_track_checks_for_double_click(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'change_track', return_value=True):

        assert provider.backend.supports_events
        is_double_click_mock = mock.PropertyMock()
        process_click_mock = mock.PropertyMock()
        provider._double_click_handler.is_double_click = is_double_click_mock
        provider._double_click_handler.process_click = process_click_mock
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
        provider._double_click_handler.set_click()
        provider.active_track_uri = track_0
        provider.change_track(models.Track(uri=track_1))

        provider._double_click_handler.process_click.assert_called_once_with(config['pandora']['on_pause_next_click'],
                                                                             provider.active_track_uri)

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
                    conftest.playlist_result_mock()["items"][0],
                    conftest.MOCK_DEFAULT_AUDIO_QUALITY))


def test_change_track_enforces_skip_limit(provider):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=False):

                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert PlaylistItem.get_is_playable.call_count == 4


def test_change_track_handles_request_exceptions(config, caplog):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.request_exception_mock):

            track = models.Track(uri="pandora:track:test::::")

            playback = conftest.get_backend(config).playback

            assert playback.change_track(track) is False
            assert 'Error changing track' in caplog.text()


def test_is_playable_handles_request_exceptions(provider, caplog):
    with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', conftest.request_exception_mock):

                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert 'Error checking if track is playable' in caplog.text()


def test_translate_uri_returns_audio_url(provider):

    assert provider.translate_uri("pandora:track:test:::::audio_url") == "audio_url"


def test_auto_set_repeat_off_for_non_pandora_uri(provider):
    with mock.patch.object(RPCClient, 'set_repeat', mock.Mock()):
        with mock.patch.object(RPCClient, 'get_current_track_uri', return_value="not_a_pandora_uri::::::"):

            provider.callback()

            assert not provider.backend.rpc_client.set_repeat.called


def test_auto_set_repeat_on_for_pandora_uri(provider):
    with mock.patch.object(RPCClient, 'set_repeat', mock.Mock()):
        with mock.patch.object(RPCClient, 'get_current_track_uri', return_value="pandora::::::"):

            provider.callback()

            provider.backend.rpc_client.set_repeat.assert_called_once_with()
