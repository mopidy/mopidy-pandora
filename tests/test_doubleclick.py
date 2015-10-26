from __future__ import unicode_literals

import time

import conftest

import mock

import pytest


from mopidy_pandora.backend import MopidyPandoraAPIClient
from mopidy_pandora.doubleclick import DoubleClickHandler
from mopidy_pandora.playback import PandoraPlaybackProvider
from mopidy_pandora.uri import PandoraUri, TrackUri


@pytest.fixture(scope="session")
def client_mock():
    client_mock = mock.Mock(spec=MopidyPandoraAPIClient)
    return client_mock


@pytest.fixture
def handler(config):
    handler = DoubleClickHandler(config['pandora'], client_mock)
    add_feedback_mock = mock.PropertyMock()
    handler.client.add_feedback = add_feedback_mock

    sleep_mock = mock.PropertyMock()
    handler.client.sleep_song = sleep_mock

    handler.set_click_time()

    return handler


def test_is_double_click(handler):

    assert handler.is_double_click()

    time.sleep(float(handler.double_click_interval) + 0.1)
    assert handler.is_double_click() is False


def test_is_double_click_resets_click_time(handler):

    assert handler.is_double_click()

    time.sleep(float(handler.double_click_interval) + 0.1)
    assert handler.is_double_click() is False

    assert handler.get_click_time() == 0


def test_on_change_track_forward(config, handler, playlist_item_mock):

    track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
    track_1 = TrackUri.from_track(playlist_item_mock, 1).uri
    track_2 = TrackUri.from_track(playlist_item_mock, 2).uri

    process_click_mock = mock.PropertyMock()
    handler.process_click = process_click_mock

    handler.on_change_track(track_0, track_1)
    handler.process_click.assert_called_with(config['pandora']['on_pause_next_click'], track_0)
    handler.on_change_track(track_1, track_2)
    handler.process_click.assert_called_with(config['pandora']['on_pause_next_click'], track_1)
    handler.on_change_track(track_2, track_0)
    handler.process_click.assert_called_with(config['pandora']['on_pause_next_click'], track_2)


def test_on_change_track_back(config, handler, playlist_item_mock):

    track_0 = TrackUri.from_track(playlist_item_mock, 0).uri
    track_1 = TrackUri.from_track(playlist_item_mock, 1).uri
    track_2 = TrackUri.from_track(playlist_item_mock, 2).uri

    process_click_mock = mock.PropertyMock()
    handler.process_click = process_click_mock

    handler.on_change_track(track_2, track_1)
    handler.process_click.assert_called_with(config['pandora']['on_pause_previous_click'], track_2)
    handler.on_change_track(track_1, track_0)
    handler.process_click.assert_called_with(config['pandora']['on_pause_previous_click'], track_1)
    handler.on_change_track(track_0, track_0)
    handler.process_click.assert_called_with(config['pandora']['on_pause_previous_click'], track_0)


def test_on_resume_click_ignored_if_start_of_track(handler, playlist_item_mock):

    process_click_mock = mock.PropertyMock()
    handler.process_click = process_click_mock
    handler.on_resume_click(TrackUri.from_track(playlist_item_mock).uri, 0)

    handler.process_click.assert_not_called()


def test_on_resume_click(config, handler, playlist_item_mock):
    with mock.patch.object(PandoraPlaybackProvider, 'get_time_position', return_value=100):

        process_click_mock = mock.PropertyMock()
        handler.process_click = process_click_mock

        track_uri = TrackUri.from_track(playlist_item_mock).uri
        handler.on_resume_click(track_uri, 100)

        handler.process_click.assert_called_once_with(config['pandora']['on_pause_resume_click'], track_uri)


def test_process_click_resets_click_time(config, handler, playlist_item_mock):

    thumbs_up_mock = mock.PropertyMock()

    handler.thumbs_up = thumbs_up_mock

    track_uri = TrackUri.from_track(playlist_item_mock).uri

    handler.process_click(config['pandora']['on_pause_resume_click'], track_uri)

    assert handler.get_click_time() == 0


def test_process_click_resume(config, handler, playlist_item_mock):

    thumbs_up_mock = mock.PropertyMock()

    handler.thumbs_up = thumbs_up_mock

    track_uri = TrackUri.from_track(playlist_item_mock).uri

    handler.process_click(config['pandora']['on_pause_resume_click'], track_uri)

    token = PandoraUri.parse(track_uri).token
    handler.thumbs_up.assert_called_once_with(token)


def test_process_click_next(config, handler, playlist_item_mock):

    thumbs_down_mock = mock.PropertyMock()

    handler.thumbs_down = thumbs_down_mock

    track_uri = TrackUri.from_track(playlist_item_mock).uri

    handler.process_click(config['pandora']['on_pause_next_click'], track_uri)

    token = PandoraUri.parse(track_uri).token
    handler.thumbs_down.assert_called_once_with(token)


def test_process_click_previous(config, handler, playlist_item_mock):

    sleep_mock = mock.PropertyMock()

    handler.sleep = sleep_mock

    track_uri = TrackUri.from_track(playlist_item_mock).uri

    handler.process_click(config['pandora']['on_pause_previous_click'], track_uri)

    token = PandoraUri.parse(track_uri).token
    handler.sleep.assert_called_once_with(token)


def test_thumbs_up(handler):

    handler.thumbs_up(conftest.MOCK_TRACK_TOKEN)

    handler.client.add_feedback.assert_called_once_with(conftest.MOCK_TRACK_TOKEN, True)


def test_thumbs_down(handler):

    handler.thumbs_down(conftest.MOCK_TRACK_TOKEN)

    handler.client.add_feedback.assert_called_once_with(conftest.MOCK_TRACK_TOKEN, False)


def test_sleep(handler):

    handler.sleep(conftest.MOCK_TRACK_TOKEN)

    handler.client.sleep_song.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)


def add_artist_bookmark(handler):

    handler.add_artist_bookmark(conftest.MOCK_TRACK_TOKEN)

    handler.client.add_artist_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)


def add_song_bookmark(handler):

    handler.add_song_bookmark(conftest.MOCK_TRACK_TOKEN)

    handler.client.add_song_bookmark.assert_called_once_with(conftest.MOCK_TRACK_TOKEN)
