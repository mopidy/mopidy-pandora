from __future__ import absolute_import, division, print_function, unicode_literals

import time

import mock

from pandora import APIClient
from pandora.models.pandora import GenreStationList, StationList

import pytest

from mopidy_pandora.client import MopidyAPIClient

from . import conftest


def test_get_genre_stations(config):
    with mock.patch.object(APIClient, 'get_genre_stations', conftest.get_genre_stations_mock):
        backend = conftest.get_backend(config)

        genre_stations = backend.api.get_genre_stations()

        assert len(genre_stations) == len(conftest.genre_stations_result_mock()['categories'])
        assert 'Category mock' in list(genre_stations)


def test_get_genre_stations_handles_request_exception(config, caplog):
    backend = conftest.get_backend(config, True)

    assert backend.api.get_genre_stations() == []

    # Check that request exceptions are caught and logged
    assert 'Error retrieving Pandora genre stations.' in caplog.text()


def test_get_genre_stations_populates_cache(config):
    with mock.patch.object(APIClient, 'get_genre_stations', conftest.get_genre_stations_mock):
        backend = conftest.get_backend(config)

        assert backend.api.genre_stations_cache.currsize == 0

        backend.api.get_genre_stations()
        assert backend.api.genre_stations_cache.currsize == 1


def test_get_genre_stations_changed_cached(config):
    with mock.patch.object(APIClient, 'get_genre_stations', conftest.get_genre_stations_mock):
        # Ensure that the cache is re-used between calls
        backend = conftest.get_backend(config)

        cached_checksum = 'zz00aa00aa00aa00aa00aa00aa00aa99'
        mock_cached_result = {'stat': 'ok',
                              'result': {
                                  'categories': [{
                                      'stations': [{
                                          'stationToken': 'G200',
                                          'stationName': 'Genre mock2',
                                          'stationId': 'G200'
                                      }],
                                      'categoryName': 'Category mock2'
                                  }],
                              }}

        station_list = GenreStationList.from_json(APIClient, mock_cached_result['result'])
        station_list.checksum = cached_checksum
        backend.api.genre_stations_cache[time.time()] = station_list

        assert backend.api.get_genre_stations().checksum == cached_checksum
        assert len(backend.api.genre_stations_cache.values()[0]) == len(GenreStationList.from_json(
            APIClient, mock_cached_result['result']))


def test_getgenre_stations_cache_disabled(config):
    with mock.patch.object(APIClient, 'get_genre_stations', conftest.get_genre_stations_mock):
        cache_config = config
        cache_config['pandora']['cache_time_to_live'] = 0
        backend = conftest.get_backend(cache_config)

        assert backend.api.genre_stations_cache.currsize == 0

        assert len(backend.api.get_genre_stations()) == 1
        assert backend.api.genre_stations_cache.currsize == 0


def test_get_station_list(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        backend = conftest.get_backend(config)

        station_list = backend.api.get_station_list()

        assert len(station_list) == len(conftest.station_list_result_mock()['stations'])
        assert station_list[0].name == conftest.MOCK_STATION_NAME + ' 2'
        assert station_list[1].name == conftest.MOCK_STATION_NAME + ' 1'
        assert station_list[2].name.startswith('QuickMix')


def test_get_station_list_populates_cache(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        backend = conftest.get_backend(config)

        assert backend.api.station_list_cache.currsize == 0

        backend.api.get_station_list()
        assert backend.api.station_list_cache.currsize == 1


def test_get_station_list_changed_cached(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        # Ensure that the cache is re-used between calls
        backend = conftest.get_backend(config)

        cached_checksum = 'zz00aa00aa00aa00aa00aa00aa00aa99'
        mock_cached_result = {'stat': 'ok',
                              'result': {
                                  'stations': [
                                        {'stationId': conftest.MOCK_STATION_ID,
                                         'stationToken': conftest.MOCK_STATION_TOKEN,
                                         'stationName': conftest.MOCK_STATION_NAME
                                         }, ],
                                  'checksum': cached_checksum
                              }}

        backend.api.station_list_cache[time.time()] = StationList.from_json(
            APIClient, mock_cached_result['result'])

        assert backend.api.get_station_list().checksum == cached_checksum
        assert len(backend.api.station_list_cache.values()[0]) == len(StationList.from_json(
            APIClient, mock_cached_result['result']))


def test_getstation_list_cache_disabled(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        cache_config = config
        cache_config['pandora']['cache_time_to_live'] = 0
        backend = conftest.get_backend(cache_config)

        assert backend.api.station_list_cache.currsize == 0

        assert len(backend.api.get_station_list()) == 3
        assert backend.api.station_list_cache.currsize == 0


def test_get_station_list_changed_refreshed(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        # Ensure that the cache is invalidated if 'force_refresh' is True
        with mock.patch.object(StationList, 'has_changed', return_value=True):
            backend = conftest.get_backend(config)

            cached_checksum = 'zz00aa00aa00aa00aa00aa00aa00aa99'
            mock_cached_result = {'stat': 'ok',
                                  'result': {
                                      'stations': [
                                            {'stationId': conftest.MOCK_STATION_ID,
                                             'stationToken': conftest.MOCK_STATION_TOKEN,
                                             'stationName': conftest.MOCK_STATION_NAME
                                             }, ],
                                      'checksum': cached_checksum
                                  }}

            backend.api.station_list_cache[time.time()] = StationList.from_json(
                APIClient, mock_cached_result['result'])

            assert backend.api.get_station_list().checksum == cached_checksum

            assert backend.api.get_station_list(force_refresh=True).checksum == conftest.MOCK_STATION_LIST_CHECKSUM
            assert (len(backend.api.station_list_cache.values()[0]) ==
                    len(conftest.station_list_result_mock()['stations']))


def test_get_station_list_handles_request_exception(config, caplog):
    backend = conftest.get_backend(config, True)

    assert backend.api.get_station_list() == []

    # Check that request exceptions are caught and logged
    assert 'Error retrieving Pandora station list.' in caplog.text()


def test_get_station(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        # Make sure we re-use the cached station list between calls
        with mock.patch.object(StationList, 'has_changed', return_value=False):
            backend = conftest.get_backend(config)

            backend.api.get_station_list()

            assert backend.api.get_station(
                conftest.MOCK_STATION_TOKEN).name == conftest.MOCK_STATION_NAME + ' 1'

            assert backend.api.get_station(
                conftest.MOCK_STATION_TOKEN.replace('1', '2')).name == conftest.MOCK_STATION_NAME + ' 2'


def test_get_invalid_station(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        # Check that a call to the Pandora server is triggered if station is
        # not found in the cache
        with pytest.raises(conftest.TransportCallTestNotImplemented):

            backend = conftest.get_backend(config)

            backend.api.get_station('9999999999999999999')


def test_create_genre_station_invalidates_cache(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        with mock.patch.object(MopidyAPIClient, 'get_genre_stations', conftest.get_genre_stations_mock):
            backend = conftest.get_backend(config)

            backend.api.create_station = mock.PropertyMock(return_value=conftest.station_result_mock()['result'])
            t = time.time()
            backend.api.station_list_cache[t] = mock.Mock(spec=StationList)
            assert t in list(backend.api.station_list_cache)

            backend.library._create_station_for_token('test_token')
            assert t not in list(backend.api.station_list_cache)
            assert backend.api.station_list_cache.currsize == 1
