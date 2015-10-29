from __future__ import unicode_literals

import conftest

import mock

from mopidy import models

from pandora import APIClient
from pandora.models.pandora import Station

from mopidy_pandora.uri import StationUri, TrackUri

from tests.conftest import get_station_list_mock


def test_lookup_of_invalid_uri(config, caplog):
    backend = conftest.get_backend(config)

    results = backend.library.lookup('pandora:invalid')

    assert len(results) == 0
    assert "Failed to lookup 'pandora:invalid'" in caplog.text()


def test_lookup_of_track_uri(config, playlist_item_mock):

    backend = conftest.get_backend(config)

    track_uri = TrackUri.from_track(playlist_item_mock)
    results = backend.library.lookup(track_uri.uri)

    assert len(results) == 1

    track = results[0]

    assert track.name == track_uri.name
    assert track.uri == track_uri.uri
    assert next(iter(track.artists)).name == "Pandora"
    assert track.album.name == track_uri.name
    assert track.album.uri == track_uri.detail_url
    assert next(iter(track.album.images)) == track_uri.art_url


def test_browse_directory_uri(config, caplog):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        backend = conftest.get_backend(config)
        results = backend.library.browse(backend.library.root_directory.uri)

        assert len(results) == 2
        assert results[0].type == models.Ref.DIRECTORY
        assert results[0].name == conftest.MOCK_STATION_NAME + " 2"
        assert results[0].uri == StationUri.from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()["stations"][0])).uri

        assert results[0].type == models.Ref.DIRECTORY
        assert results[1].name == conftest.MOCK_STATION_NAME + " 1"
        assert results[1].uri == StationUri.from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()["stations"][1])).uri


def test_browse_directory_sort_za(config, caplog):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        config['pandora']['sort_order'] = 'A-Z'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == conftest.MOCK_STATION_NAME + " 1"
        assert results[1].name == conftest.MOCK_STATION_NAME + " 2"


def test_browse_directory_sort_date(config, caplog):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        config['pandora']['sort_order'] = 'date'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == conftest.MOCK_STATION_NAME + " 2"
        assert results[1].name == conftest.MOCK_STATION_NAME + " 1"


def test_browse_track_uri(config, playlist_item_mock, caplog):

    backend = conftest.get_backend(config)
    track_uri = TrackUri.from_track(playlist_item_mock)

    results = backend.library.browse(track_uri.uri)

    assert len(results) == 3

    backend.supports_events = False

    results = backend.library.browse(track_uri.uri)
    assert len(results) == 1

    assert results[0].type == models.Ref.TRACK
    assert results[0].name == track_uri.name
    assert TrackUri.parse(results[0].uri).index == str(0)

    # Track should not have an audio URL at this stage
    assert TrackUri.parse(results[0].uri).audio_url == "none_generated"

    # Also clear reference track's audio URI so that we can compare more easily
    track_uri.audio_url = "none_generated"
    assert results[0].uri == track_uri.uri
