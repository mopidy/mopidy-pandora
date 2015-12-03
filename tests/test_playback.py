from __future__ import unicode_literals

import threading
import time

import conftest

import mock

from mopidy import audio, backend as backend_api, models

from pandora.models.pandora import PlaylistItem

import pytest

from mopidy_pandora import playback, rpc

from mopidy_pandora.backend import MopidyPandoraAPIClient
from mopidy_pandora.library import PandoraLibraryProvider

from mopidy_pandora.playback import EventSupportPlaybackProvider, PandoraPlaybackProvider

from mopidy_pandora.uri import PandoraUri, TrackUri


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def provider(audio_mock, config):

    provider = None

    if config['pandora']['event_support_enabled']:
        provider = playback.EventSupportPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))

        provider.current_tl_track = {'track': {'uri': 'test'}}

        provider._sync_tracklist = mock.PropertyMock()
    else:
        provider = playback.PandoraPlaybackProvider(
            audio=audio_mock, backend=conftest.get_backend(config))

    return provider


@pytest.fixture(scope="session")
def client_mock():
    client_mock = mock.Mock(spec=MopidyPandoraAPIClient)
    return client_mock


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_change_track_aborts_if_no_track_uri(provider):
    track = models.Track(uri=None)

    assert provider.change_track(track) is False


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


def test_change_track_enforces_skip_limit(provider, playlist_item_mock, caplog):
    with mock.patch.object(EventSupportPlaybackProvider, 'is_double_click', return_value=False):
        with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=None):
            track = TrackUri.from_track(playlist_item_mock)

            process_click_mock = mock.PropertyMock()
            provider.process_click = process_click_mock

            provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
            provider.next_tl_track = {'track': {'uri': track.uri}}

            rpc.RPCClient.playback_stop = mock.PropertyMock()

            for i in range(PandoraPlaybackProvider.SKIP_LIMIT+1):
                provider.change_track(track) is False

            assert rpc.RPCClient.playback_stop.called
            assert "Maximum track skip limit (%s) exceeded, stopping...", \
                PandoraPlaybackProvider.SKIP_LIMIT in caplog.text()

    # with mock.patch.object(MopidyPandoraAPIClient, 'get_station', conftest.get_station_mock):
    #     with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):
    #         with mock.patch.object(PlaylistItem, 'get_is_playable', return_value=False):
    #             track = models.Track(uri="pandora:track:test_station_id:test_token")
    #
    #             rpc.RPCClient.playback_stop = mock.PropertyMock()
    #
    #             assert provider.change_track(track) is False
    #             rpc.RPCClient.playback_stop.assert_called_once_with()
    #             assert PlaylistItem.get_is_playable.call_count == PandoraPlaybackProvider.SKIP_LIMIT


def test_change_track_resumes_playback(provider, playlist_item_mock):
    with mock.patch.object(EventSupportPlaybackProvider, 'is_double_click', return_value=True):
        track = TrackUri.from_track(playlist_item_mock)

        process_click_mock = mock.PropertyMock()
        provider.process_click = process_click_mock

        provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
        provider.next_tl_track = {'track': {'uri': track.uri}}

        rpc.RPCClient.playback_resume = mock.PropertyMock()

        provider.change_track(track)
        assert rpc.RPCClient.playback_resume.called


def test_change_track_does_not_resume_playback_if_not_doubleclick(provider, playlist_item_mock):
    with mock.patch.object(EventSupportPlaybackProvider, 'is_double_click', return_value=False):
        track = TrackUri.from_track(playlist_item_mock)

        process_click_mock = mock.PropertyMock()
        provider.process_click = process_click_mock

        provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
        provider.next_tl_track = {'track': {'uri': track.uri}}

        rpc.RPCClient.playback_resume = mock.PropertyMock()

        provider.change_track(track)
        assert not rpc.RPCClient.playback_resume.called


def test_change_track_handles_request_exceptions(config, caplog, playlist_item_mock):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        with mock.patch.object(PlaylistItem, 'get_is_playable', conftest.request_exception_mock):

            track = models.Track(uri="pandora:track:test_station_id:test_token")

            playback = conftest.get_backend(config, True).playback

            rpc.RPCClient._do_rpc = mock.PropertyMock()
            rpc.RPCClient.playback_stop = mock.PropertyMock()

            rpc.RPCClient.playback_resume = mock.PropertyMock()

            assert playback.change_track(track) is False
            assert 'Error checking if track is playable' in caplog.text()


def test_change_track_handles_unplayable(provider, caplog):

        track = models.Track(uri="pandora:track:test_station_id:test_token")

        provider.previous_tl_track = {'track': {'uri': track.uri}}
        provider.next_tl_track = {'track': {'uri': 'next_track'}}

        rpc.RPCClient.playback_resume = mock.PropertyMock()

        assert provider.change_track(track) is False
        assert "Audio URI for track '%s' cannot be played", track.uri in caplog.text()


def test_translate_uri_returns_audio_url(provider, playlist_item_mock):

    test_uri = "pandora:track:test_station_id:test_token"

    provider.backend.library._uri_translation_map[test_uri] = playlist_item_mock

    assert provider.translate_uri(test_uri) == conftest.MOCK_TRACK_AUDIO_HIGH


def test_auto_setup_only_called_once(provider):
    with mock.patch.multiple('mopidy_pandora.rpc.RPCClient', tracklist_set_repeat=mock.DEFAULT,
                             tracklist_set_random=mock.DEFAULT, tracklist_set_consume=mock.DEFAULT,
                             tracklist_set_single=mock.DEFAULT) as values:

        event = threading.Event()

        def set_event(*args, **kwargs):
            event.set()

        values['tracklist_set_single'].side_effect = set_event

        provider.prepare_change()

        if event.wait(timeout=1.0):
            values['tracklist_set_repeat'].assert_called_once_with(False)
            values['tracklist_set_random'].assert_called_once_with(False)
            values['tracklist_set_consume'].assert_called_once_with(True)
            values['tracklist_set_single'].assert_called_once_with(False)
        else:
            assert False

        event = threading.Event()
        values['tracklist_set_single'].side_effect = set_event

        provider.prepare_change()

        if event.wait(timeout=1.0):
            assert False
        else:
            values['tracklist_set_repeat'].assert_called_once_with(False)
            values['tracklist_set_random'].assert_called_once_with(False)
            values['tracklist_set_consume'].assert_called_once_with(True)
            values['tracklist_set_single'].assert_called_once_with(False)


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


def test_change_track_next(config, provider, playlist_item_mock):

    provider.set_click_time()
    track = TrackUri.from_track(playlist_item_mock)

    process_click_mock = mock.PropertyMock()
    provider.process_click = process_click_mock

    provider.previous_tl_track = {'track': {'uri': 'previous_track'}}
    provider.next_tl_track = {'track': {'uri': track.uri}}

    rpc.RPCClient._do_rpc = mock.PropertyMock()

    provider.change_track(track)
    provider.process_click.assert_called_with(config['pandora']['on_pause_next_click'], track.uri)


def test_change_track_back(config, provider, playlist_item_mock):

    provider.set_click_time()
    track = TrackUri.from_track(playlist_item_mock)

    process_click_mock = mock.PropertyMock()
    provider.process_click = process_click_mock

    provider.previous_tl_track = {'track': {'uri': track.uri}}
    provider.next_tl_track = {'track': {'uri': 'next_track'}}

    rpc.RPCClient._do_rpc = mock.PropertyMock()

    provider.change_track(track)
    provider.process_click.assert_called_with(config['pandora']['on_pause_previous_click'], track.uri)


def test_resume_click_ignored_if_start_of_track(provider):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=0):

        process_click_mock = mock.PropertyMock()
        provider.process_click = process_click_mock

        provider.resume()

        provider.process_click.assert_not_called()


def test_process_click_resets_click_time(config, provider, playlist_item_mock):

    provider.thumbs_up = mock.PropertyMock()

    track_uri = TrackUri.from_track(playlist_item_mock).uri

    provider.process_click(config['pandora']['on_pause_resume_click'], track_uri)

    assert provider.get_click_time() == 0


def test_process_click_triggers_event(config, provider, playlist_item_mock):
    with mock.patch.object(PandoraLibraryProvider, 'lookup_pandora_track', return_value=playlist_item_mock):
        with mock.patch.multiple(EventSupportPlaybackProvider, thumbs_up=mock.PropertyMock(),
                                 thumbs_down=mock.PropertyMock(), sleep=mock.PropertyMock()):

            track_uri = TrackUri.from_track(playlist_item_mock).uri

            method = config['pandora']['on_pause_next_click']
            method_call = getattr(provider, method)

            t = provider.process_click(method, track_uri)
            t.join()

            token = PandoraUri.parse(track_uri).token
            method_call.assert_called_once_with(token)


def add_artist_bookmark(provider):

    provider.add_artist_bookmark(conftest.MOCK_TRACK_TOKEN)

    provider.client.add_artist_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)


def add_song_bookmark(provider):

    provider.add_song_bookmark(conftest.MOCK_TRACK_TOKEN)

    provider.client.add_song_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)
