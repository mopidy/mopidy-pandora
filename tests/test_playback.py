from __future__ import unicode_literals

import conftest

import mock

from mopidy import audio, backend as backend_api, models

from pandora.models.pandora import PlaylistItem, Station

import pytest

from mopidy_pandora import actor, client


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def provider(audio_mock, config):
    return actor.PandoraPlaybackProvider(
        audio=audio_mock, backend=conftest.get_backend(config))


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_change_track_aborts_if_no_track_uri(provider):
    track = models.Track()

    assert provider.change_track(track) is False


def test_change_track(audio_mock, provider):
    with mock.patch.object(client.MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=True):

                track = models.Track(uri=actor.TrackUri.from_track(conftest.playlist_item_mock()).uri)

                assert provider.change_track(track) is True
                assert audio_mock.prepare_change.call_count == 0
                assert audio_mock.start_playback.call_count == 0
                audio_mock.set_uri.assert_called_once_with(PlaylistItem.get_audio_url(
                    conftest.playlist_result_mock()["items"][0],
                    conftest.MOCK_DEFAULT_AUDIO_QUALITY))


def test_change_track_enforces_skip_limit(provider):
    with mock.patch.object(client.MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=False):

                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert PlaylistItem.get_is_playable.call_count == 4


def test_change_track_handles_request_exceptions(config, caplog):
    with mock.patch.object(client.MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_request_exception_mock):

            track = models.Track(uri="pandora:track:test::::")

            playback = conftest.get_backend(config).playback

            assert playback.change_track(track) is False
            assert 'Error changing track' in caplog.text()


def test_is_playable_handles_request_exceptions(provider, caplog):
    with mock.patch.object(client.MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
            with mock.patch.object(PlaylistItem, 'get_is_playable', conftest.get_is_playable_request_exception_mock):

                track = models.Track(uri="pandora:track:test::::")

                assert provider.change_track(track) is False
                assert 'Error checking if track is playable' in caplog.text()


def test_translate_uri_returns_audio_url(provider):

    assert provider.translate_uri("pandora:track:test:::::audio_url") == "audio_url"
