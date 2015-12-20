from __future__ import unicode_literals

import conftest

import mock

from mopidy import models

from pandora import APIClient
from pandora.models.pandora import Station

import pytest

from mopidy_pandora.client import MopidyAPIClient
from mopidy_pandora.library import PandoraLibraryProvider

from mopidy_pandora.uri import PandoraUri, PlaylistItemUri, StationUri, TrackUri

from tests.conftest import get_station_list_mock


def test_lookup_of_invalid_uri(config, caplog):
    with pytest.raises(ValueError):
        backend = conftest.get_backend(config)

        backend.library.lookup('pandora:invalid')


def test_lookup_of_track_uri(config, playlist_item_mock):

    backend = conftest.get_backend(config)

    track_uri = PlaylistItemUri.from_track(playlist_item_mock)
    backend.library._pandora_track_buffer[track_uri.uri] = playlist_item_mock

    results = backend.library.lookup(track_uri.uri)

    assert len(results) == 1

    track = results[0]

    assert track.uri == track_uri.uri


def test_lookup_of_missing_track(config, playlist_item_mock, caplog):

    backend = conftest.get_backend(config)

    track_uri = TrackUri.from_track(playlist_item_mock)
    results = backend.library.lookup(track_uri.uri)

    assert len(results) == 0

    assert 'Failed to lookup \'{}\''.format(track_uri.uri) in caplog.text()


def test_browse_directory_uri(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        backend = conftest.get_backend(config)
        results = backend.library.browse(backend.library.root_directory.uri)

        assert len(results) == 4

        assert results[0].type == models.Ref.DIRECTORY
        assert results[0].name == PandoraLibraryProvider.GENRE_DIR_NAME
        assert results[0].uri == PandoraUri('genres').uri

        assert results[1].type == models.Ref.DIRECTORY
        assert results[1].name == 'QuickMix'
        assert results[1].uri == StationUri.from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][2])).uri

        assert results[2].type == models.Ref.DIRECTORY
        assert results[2].name == conftest.MOCK_STATION_NAME + ' 2'
        assert results[2].uri == StationUri.from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][0])).uri

        assert results[3].type == models.Ref.DIRECTORY
        assert results[3].name == conftest.MOCK_STATION_NAME + ' 1'
        assert results[3].uri == StationUri.from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][1])).uri


def test_browse_directory_sort_za(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        config['pandora']['sort_order'] = 'A-Z'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == PandoraLibraryProvider.GENRE_DIR_NAME
        assert results[1].name == 'QuickMix'
        assert results[2].name == conftest.MOCK_STATION_NAME + ' 1'
        assert results[3].name == conftest.MOCK_STATION_NAME + ' 2'


def test_browse_directory_sort_date(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):

        config['pandora']['sort_order'] = 'date'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == PandoraLibraryProvider.GENRE_DIR_NAME
        assert results[1].name == 'QuickMix'
        assert results[2].name == conftest.MOCK_STATION_NAME + ' 2'
        assert results[3].name == conftest.MOCK_STATION_NAME + ' 1'


def test_browse_station_uri(config, station_mock):
    with mock.patch.object(MopidyAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):

            backend = conftest.get_backend(config)
            station_uri = StationUri.from_station(station_mock)

            results = backend.library.browse(station_uri.uri)

            # Station should just contain the first track to be played.
            assert len(results) == 1
