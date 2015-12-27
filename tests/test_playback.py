from __future__ import unicode_literals

import time

import conftest

import mock

from mopidy import audio, backend as backend_api, models

from pandora import APITransport

import pytest

from mopidy_pandora import playback

from mopidy_pandora.backend import MopidyAPIClient
from mopidy_pandora.library import PandoraLibraryProvider

from mopidy_pandora.playback import EventHandlingPlaybackProvider, PandoraPlaybackProvider

from mopidy_pandora.uri import PandoraUri


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def provider(audio_mock, config):

    provider = None

    if config['pandora']['event_support_enabled']:
        provider = playback.EventHandlingPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))

        provider.current_tl_track = {'track': {'uri': 'test'}}

        provider._sync_tracklist = mock.PropertyMock()
    else:
        provider = playback.PandoraPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))

    return provider


@pytest.fixture(scope='session')
def client_mock():
    client_mock = mock.Mock(spec=MopidyAPIClient)
    return client_mock


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_pause_starts_double_click_timer(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):
        assert provider.backend.supports_events
        assert provider.get_click_time() == 0
        provider.pause()
        assert provider.get_click_time() > 0


def test_pause_does_not_start_timer_at_track_start(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=0):
        assert provider.backend.supports_events
        assert provider.get_click_time() == 0
        provider.pause()
        assert provider.get_click_time() == 0


def test_resume_checks_for_double_click(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):
        assert provider.backend.supports_events
        is_double_click_mock = mock.PropertyMock()
        process_click_mock = mock.PropertyMock()
        provider.is_double_click = is_double_click_mock
        provider.process_click = process_click_mock
        provider.resume()

        provider.is_double_click.assert_called_once_with()


def test_change_track_enforces_skip_limit_if_no_track_available(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventHandlingPlaybackProvider, 'is_double_click', return_value=False):
        with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=None):
            track = PandoraUri.factory(playlist_item_mock)

            provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
            provider.next_tl_track = {'track': {'uri': track.uri}}

            provider.backend.prepare_next_track = mock.PropertyMock()
            provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)

            for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
                assert provider.change_track(track) is False
                if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                    assert provider.backend.prepare_next_track.called
                    provider.backend.prepare_next_track.reset_mock()
                    assert not provider._trigger_skip_limit_exceeded.called
                else:
                    assert not provider.backend.prepare_next_track.called
                    assert provider._trigger_skip_limit_exceeded.called

            assert 'Maximum track skip limit ({:d}) exceeded.'.format(
                PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_enforces_skip_limit_if_no_audio_url(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventHandlingPlaybackProvider, 'is_double_click', return_value=False):
        with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
            track = PandoraUri.factory(playlist_item_mock)

            provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
            provider.next_tl_track = {'track': {'uri': track.uri}}

            provider.backend.prepare_next_track = mock.PropertyMock()
            provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)

            playlist_item_mock.audio_url = None

            for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
                assert provider.change_track(track) is False
                if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                    assert provider.backend.prepare_next_track.called
                    provider.backend.prepare_next_track.reset_mock()
                    assert not provider._trigger_skip_limit_exceeded.called
                else:
                    assert not provider.backend.prepare_next_track.called
                    assert provider._trigger_skip_limit_exceeded.called

            assert 'Maximum track skip limit ({:d}) exceeded.'.format(
                PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_enforces_skip_limit_on_request_exceptions(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventHandlingPlaybackProvider, 'is_double_click', return_value=False):
        with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
            with mock.patch.object(APITransport, '__call__', side_effect=conftest.request_exception_mock):
                track = PandoraUri.factory(playlist_item_mock)

                provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
                provider.next_tl_track = {'track': {'uri': track.uri}}

                provider.backend.prepare_next_track = mock.PropertyMock()
                provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)
                playlist_item_mock.audio_url = 'pandora:track:mock_id:mock_token'

                for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
                    assert provider.change_track(track) is False
                    if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                        assert provider.backend.prepare_next_track.called
                        provider.backend.prepare_next_track.reset_mock()
                        assert not provider._trigger_skip_limit_exceeded.called
                    else:
                        assert not provider.backend.prepare_next_track.called
                        assert provider._trigger_skip_limit_exceeded.called

                assert 'Maximum track skip limit ({:d}) exceeded.'.format(
                    PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_fetches_next_track_if_unplayable(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventHandlingPlaybackProvider, 'is_double_click', return_value=False):
        with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=None):
            track = PandoraUri.factory(playlist_item_mock)

            provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
            provider.next_tl_track = {'track': {'uri': track.uri}}

            provider.backend.prepare_next_track = mock.PropertyMock()

            assert provider.change_track(track) is False
            assert provider.backend.prepare_next_track.called

            assert 'Skipping to next Pandora track...' in caplog.text()


def test_change_track_skips_if_no_track_uri(provider):
    track = models.Track(uri=None)

    provider.change_pandora_track = mock.PropertyMock()
    assert provider.change_track(track) is False
    assert not provider.change_pandora_track.called


def test_change_track_skips_if_track_not_available_in_buffer(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventHandlingPlaybackProvider, 'is_double_click', return_value=False):
        track = PandoraUri.factory(playlist_item_mock)

        provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
        provider.next_tl_track = {'track': {'uri': track.uri}}

        provider.backend.prepare_next_track = mock.PropertyMock()

        assert provider.change_track(track) is False
        assert "Error changing Pandora track: failed to lookup '{}'.".format(track.uri) in caplog.text()


def test_translate_uri_returns_audio_url(provider, playlist_item_mock):

    test_uri = 'pandora:track:test_station_id:test_token'
    provider.backend.library._pandora_track_cache[test_uri] = playlist_item_mock

    assert provider.translate_uri(test_uri) == conftest.MOCK_TRACK_AUDIO_HIGH


def test_is_double_click(provider):

    provider.set_click_time()
    assert provider.is_double_click()

    time.sleep(float(provider.double_click_interval) + 0.1)
    assert provider.is_double_click() is False


def test_is_double_click_resets_click_time(provider):

    provider.set_click_time()
    assert provider.is_double_click()

    time.sleep(float(provider.double_click_interval) + 0.1)
    assert provider.is_double_click() is False

    assert provider.get_click_time() == 0


def test_resume_click_ignored_if_start_of_track(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=0):

        process_click_mock = mock.PropertyMock()
        provider.process_click = process_click_mock

        provider.resume()

        provider.process_click.assert_not_called()


def add_artist_bookmark(provider):

    provider.add_artist_bookmark(conftest.MOCK_TRACK_TOKEN)
    provider.client.add_artist_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)


def add_song_bookmark(provider):

    provider.add_song_bookmark(conftest.MOCK_TRACK_TOKEN)
    provider.client.add_song_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)
