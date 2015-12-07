from __future__ import unicode_literals

import time

import conftest

import mock

from pandora import APIClient
from pandora.models.pandora import StationList

import pytest


from tests.conftest import get_backend
from tests.conftest import get_station_list_mock


def test_get_station_list(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        backend = get_backend(config)

        station_list = backend.api.get_station_list()

        assert len(station_list) == len(conftest.station_list_result_mock()['stations'])
        assert station_list[0].name == conftest.MOCK_STATION_NAME + " 2"
        assert station_list[1].name == conftest.MOCK_STATION_NAME + " 1"
        assert station_list[2].name == "QuickMix"


def test_get_station_list_populates_cache(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        backend = get_backend(config)

        assert backend.api._station_list_cache.currsize == 0

        backend.api.get_station_list()
        assert backend.api._station_list_cache.currsize == 1


def test_get_station_list_changed_cached(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        # Ensure that the cache is re-used between calls
        with mock.patch.object(StationList, 'has_changed', return_value=True):
            backend = get_backend(config)

            cached_checksum = "zz00aa00aa00aa00aa00aa00aa00aa99"
            mock_cached_result = {"stat": "ok",
                                  "result": {
                                      "stations": [
                                            {"stationId": conftest.MOCK_STATION_ID,
                                             "stationToken": conftest.MOCK_STATION_TOKEN,
                                             "stationName": conftest.MOCK_STATION_NAME
                                             }, ],
                                      "checksum": cached_checksum
                                  }}

            backend.api._station_list_cache[time.time()] = StationList.from_json(
                APIClient, mock_cached_result["result"])

            backend.api.get_station_list()
            assert backend.api.get_station_list().checksum == cached_checksum
            assert len(backend.api._station_list_cache.itervalues().next()) == len(StationList.from_json(
                APIClient, mock_cached_result["result"]))


def test_get_station_list_changed_refreshed(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        # Ensure that the cache is invalidated if 'force_refresh' is True
        with mock.patch.object(StationList, 'has_changed', return_value=True):
            backend = get_backend(config)

            cached_checksum = "zz00aa00aa00aa00aa00aa00aa00aa99"
            mock_cached_result = {"stat": "ok",
                                  "result": {
                                      "stations": [
                                            {"stationId": conftest.MOCK_STATION_ID,
                                             "stationToken": conftest.MOCK_STATION_TOKEN,
                                             "stationName": conftest.MOCK_STATION_NAME
                                             }, ],
                                      "checksum": cached_checksum
                                  }}

            backend.api._station_list_cache[time.time()] = StationList.from_json(
                APIClient, mock_cached_result["result"])

            assert backend.api.get_station_list().checksum == cached_checksum

            backend.api.get_station_list(force_refresh=True)
            assert backend.api.get_station_list().checksum == conftest.MOCK_STATION_LIST_CHECKSUM
            assert len(backend.api._station_list_cache.itervalues().next()) == \
                len(conftest.station_list_result_mock()['stations'])


def test_get_station_list_handles_request_exception(config, caplog):
    backend = get_backend(config, True)

    assert backend.api.get_station_list() == []

    # Check that request exceptions are caught and logged
    assert 'Error retrieving station list' in caplog.text()


def test_get_station(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        # Make sure we re-use the cached station list between calls
        with mock.patch.object(StationList, 'has_changed', return_value=False):
            backend = get_backend(config)

            backend.api.get_station_list()

            assert backend.api.get_station(
                conftest.MOCK_STATION_ID).name == conftest.MOCK_STATION_NAME + " 1"

            assert backend.api.get_station(
                conftest.MOCK_STATION_ID.replace("1", "2")).name == conftest.MOCK_STATION_NAME + " 2"


def test_get_invalid_station(config):
    with mock.patch.object(APIClient, 'get_station_list', get_station_list_mock):
        # Check that a call to the Pandora server is triggered if station is
        # not found in the cache
        with pytest.raises(conftest.TransportCallTestNotImplemented):

            backend = get_backend(config)

            backend.api.get_station("9999999999999999999")


def test_create_genre_station_invalidates_cache(config):
    backend = get_backend(config)

    backend.api.create_station = mock.PropertyMock(return_value=conftest.station_result_mock())
    backend.api._station_list_cache[time.time()] = 'test_value'
    assert backend.api._station_list_cache.currsize == 1

    backend.library._create_station_for_genre('test_token')

    assert backend.api._station_list_cache.currsize == 0
