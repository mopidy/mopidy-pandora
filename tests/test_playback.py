from __future__ import absolute_import, division, print_function, unicode_literals

import mock

from mopidy import audio, models

from pandora import APITransport
from pandora.models.pandora import PlaylistItem

import pytest

from mopidy_pandora import playback

from mopidy_pandora.backend import MopidyAPIClient
from mopidy_pandora.library import PandoraLibraryProvider, TrackCacheItem

from mopidy_pandora.playback import PandoraPlaybackProvider

from mopidy_pandora.uri import PandoraUri

from . import conftest


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def provider(audio_mock, config):
    return playback.PandoraPlaybackProvider(audio=audio_mock, backend=conftest.get_backend(config))


@pytest.fixture(scope='session')
def client_mock():
    client_mock = mock.Mock(spec=MopidyAPIClient)
    return client_mock


def test_change_track_enforces_skip_limit_if_no_track_available(provider, playlist_item_mock, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=None):
        track = PandoraUri.factory(playlist_item_mock)

        provider._trigger_track_unplayable = mock.PropertyMock()
        provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)

        for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
            assert provider.change_track(track) is False
            if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                assert provider._trigger_track_unplayable.called
                provider._trigger_track_unplayable.reset_mock()
                assert not provider._trigger_skip_limit_exceeded.called
            else:
                assert not provider._trigger_track_unplayable.called
                assert provider._trigger_skip_limit_exceeded.called

        assert 'Maximum track skip limit ({:d}) exceeded.'.format(
            PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_enforces_skip_limit_if_no_audio_url(provider, playlist_item_mock, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        track = PandoraUri.factory(playlist_item_mock)

        provider._trigger_track_unplayable = mock.PropertyMock()
        provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)

        playlist_item_mock.audio_url = None

        for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
            assert provider.change_track(track) is False
            if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                assert provider._trigger_track_unplayable.called
                provider._trigger_track_unplayable.reset_mock()
                assert not provider._trigger_skip_limit_exceeded.called
            else:
                assert not provider._trigger_track_unplayable.called
                assert provider._trigger_skip_limit_exceeded.called

        assert 'Maximum track skip limit ({:d}) exceeded.'.format(
            PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_enforces_skip_limit_on_request_exceptions(provider, playlist_item_mock, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        with mock.patch.object(APITransport, '__call__', side_effect=conftest.request_exception_mock):
            track = PandoraUri.factory(playlist_item_mock)

            provider._trigger_track_unplayable = mock.PropertyMock()
            provider._trigger_skip_limit_exceeded = mock.PropertyMock(0)
            playlist_item_mock.audio_url = 'pandora:track:mock_id:mock_token'

            for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
                assert provider.change_track(track) is False
                if i < PandoraPlaybackProvider.SKIP_LIMIT-1:
                    assert provider._trigger_track_unplayable.called
                    provider._trigger_track_unplayable.reset_mock()
                    assert not provider._trigger_skip_limit_exceeded.called
                else:
                    assert not provider._trigger_track_unplayable.called
                    assert provider._trigger_skip_limit_exceeded.called

            assert 'Maximum track skip limit ({:d}) exceeded.'.format(
                PandoraPlaybackProvider.SKIP_LIMIT) in caplog.text()


def test_change_track_fetches_next_track_if_unplayable(provider, playlist_item_mock, caplog):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=None):
        track = PandoraUri.factory(playlist_item_mock)

        provider._trigger_track_unplayable = mock.PropertyMock()

        assert provider.change_track(track) is False
        assert provider._trigger_track_unplayable.called

        assert 'Error changing Pandora track' in caplog.text()


def test_change_track_skips_if_no_track_uri(provider):
    track = models.Track(uri=None)

    provider.change_pandora_track = mock.PropertyMock()
    assert provider.change_track(track) is False
    assert not provider.change_pandora_track.called


def test_change_track_skips_if_track_not_available_in_buffer(provider, playlist_item_mock, caplog):
    track = PandoraUri.factory(playlist_item_mock)

    provider.backend.prepare_next_track = mock.PropertyMock()

    assert provider.change_track(track) is False
    assert "Error changing Pandora track: failed to lookup '{}'.".format(track.uri) in caplog.text()


def test_change_track_resets_skips_on_success(provider, playlist_item_mock):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=True):
            track = PandoraUri.factory(playlist_item_mock)

            provider._consecutive_track_skips = 1

            assert provider.change_track(track) is True
            assert provider._consecutive_track_skips == 0


def test_change_track_triggers_event_on_success(provider, playlist_item_mock):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=True):
            track = PandoraUri.factory(playlist_item_mock)

            provider._trigger_track_changing = mock.PropertyMock()

            assert provider.change_track(track) is True
            assert provider._trigger_track_changing.called


def test_translate_uri_returns_audio_url(provider, playlist_item_mock):
    test_uri = 'pandora:track:test_station_id:test_token'
    provider.backend.library.pandora_track_cache[test_uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                            playlist_item_mock)

    assert provider.translate_uri(test_uri) == conftest.MOCK_TRACK_AUDIO_HIGH


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
