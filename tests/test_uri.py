# coding=utf-8
from __future__ import unicode_literals

import conftest

from mock import mock

from pandora.models.pandora import GenreStation, Station

import pytest

from mopidy_pandora.uri import AdItemUri, GenreStationUri, GenreUri, PandoraUri, PlaylistItemUri, StationUri, TrackUri


def test_factory_unsupported_type():
    with pytest.raises(NotImplementedError):

        PandoraUri.factory(0)


def test_factory_returns_correct_station_uri_types():
        station_mock = mock.PropertyMock(spec=GenreStation)
        station_mock.id = 'Gmock'
        station_mock.token = 'Gmock'
        assert type(PandoraUri.factory(station_mock)) is GenreStationUri

        station_mock = mock.PropertyMock(spec=Station)
        station_mock.id = 'mock_id'
        station_mock.token = 'mock_token'
        assert type(PandoraUri.factory(station_mock)) is StationUri


def test_pandora_parse_mock_uri():
    uri = 'pandora:station:mock_id:mock_token'
    obj = PandoraUri._from_uri(uri)

    assert isinstance(obj, PandoraUri)
    assert type(obj) is StationUri
    assert obj.uri == uri


def test_pandora_parse_unicode_mock_uri():
    uri = PlaylistItemUri(conftest.MOCK_STATION_ID, 'Ω≈ç√∫:˜µ≤≥÷')
    obj = PandoraUri._from_uri(uri.uri)

    assert isinstance(obj, PandoraUri)
    assert obj.uri == uri.uri


def test_pandora_repr_converts_to_string():
    uri = 'pandora:station:mock_id:'
    obj = PandoraUri._from_uri(uri)

    obj.token = 0
    assert obj.uri == uri + '0'


def test_pandora_parse_none_mock_uri():
    uri = PandoraUri()
    assert uri.encode(None) == ''


def test_pandora_parse_invalid_type_raises_exception():
    with pytest.raises(NotImplementedError):

        PandoraUri()._from_uri('pandora:invalid')


def test_pandora_parse_invalid_scheme_raises_exception():
    with pytest.raises(NotImplementedError):

        PandoraUri()._from_uri('not_the_pandora_scheme:invalid')


def test_station_uri_from_station(station_mock):
    station_uri = StationUri._from_station(station_mock)

    assert station_uri.uri == '{}:{}:{}:{}'.format(PandoraUri.SCHEME,
                                                   station_uri.encode(conftest.MOCK_STATION_TYPE),
                                                   station_uri.encode(conftest.MOCK_STATION_ID),
                                                   station_uri.encode(conftest.MOCK_STATION_TOKEN))


def test_station_uri_from_station_unsupported_type(playlist_result_mock):
    with pytest.raises(NotImplementedError):

        PandoraUri._from_station(playlist_result_mock)


def test_station_uri_parse(station_mock):
    station_uri = StationUri._from_station(station_mock)

    obj = PandoraUri._from_uri(station_uri.uri)

    assert type(obj) is StationUri

    assert obj.uri_type == conftest.MOCK_STATION_TYPE
    assert obj.station_id == conftest.MOCK_STATION_ID
    assert obj.token == conftest.MOCK_STATION_TOKEN

    assert obj.uri == station_uri.uri


def test_station_uri_parse_returns_correct_type():
    station_mock = mock.PropertyMock(spec=GenreStation)
    station_mock.id = 'Gmock'
    station_mock.token = 'Gmock'

    obj = StationUri._from_station(station_mock)

    assert type(obj) is GenreStationUri


def test_genre_uri_parse():
    mock_uri = 'pandora:genre:mock_category'
    obj = PandoraUri._from_uri(mock_uri)

    assert type(obj) is GenreUri

    assert obj.uri_type == 'genre'
    assert obj.category_name == 'mock_category'

    assert obj.uri == mock_uri


def test_genre_station_uri_parse():
    mock_uri = 'pandora:genre_station:Gmock:Gmock'
    obj = PandoraUri._from_uri(mock_uri)

    assert type(obj) is GenreStationUri

    assert obj.uri_type == 'genre_station'
    assert obj.station_id == 'Gmock'
    assert obj.token == 'Gmock'

    assert obj.uri == mock_uri


def test_genre_station_uri_from_station_returns_correct_type():
    genre_mock = mock.PropertyMock(spec=Station)
    genre_mock.id = 'mock_id'
    genre_mock.token = 'mock_token'

    obj = StationUri._from_station(genre_mock)

    assert type(obj) is StationUri

    assert obj.uri_type == 'station'
    assert obj.station_id == 'mock_id'
    assert obj.token == 'mock_token'

    assert obj.uri == 'pandora:station:mock_id:mock_token'


def test_genre_station_uri_from_genre_station_returns_correct_type():
    genre_station_mock = mock.PropertyMock(spec=GenreStation)
    genre_station_mock.id = 'Gmock'
    genre_station_mock.token = 'Gmock'

    obj = GenreStationUri._from_station(genre_station_mock)

    assert type(obj) is GenreStationUri

    assert obj.uri_type == 'genre_station'
    assert obj.station_id == 'Gmock'
    assert obj.token == 'Gmock'

    assert obj.uri == 'pandora:genre_station:Gmock:Gmock'


def test_track_uri_from_track(playlist_item_mock):
    track_uri = TrackUri._from_track(playlist_item_mock)

    assert track_uri.uri == '{}:{}:{}:{}'.format(PandoraUri.SCHEME,
                                                 track_uri.encode(conftest.MOCK_TRACK_TYPE),
                                                 track_uri.encode(conftest.MOCK_STATION_ID),
                                                 track_uri.encode(conftest.MOCK_TRACK_TOKEN))


def test_track_uri_from_track_unsupported_type(playlist_result_mock):
    with pytest.raises(NotImplementedError):

        PandoraUri._from_track(playlist_result_mock)


def test_track_uri_from_track_for_ads(ad_item_mock):
    track_uri = TrackUri._from_track(ad_item_mock)

    assert track_uri.uri == '{}:{}:{}'.format(PandoraUri.SCHEME,
                                              track_uri.encode(conftest.MOCK_AD_TYPE),
                                              conftest.MOCK_STATION_ID)


def test_track_uri_parse(playlist_item_mock):
    track_uri = TrackUri._from_track(playlist_item_mock)

    obj = PandoraUri._from_uri(track_uri.uri)

    assert type(obj) is PlaylistItemUri

    assert obj.uri_type == conftest.MOCK_TRACK_TYPE
    assert obj.station_id == conftest.MOCK_STATION_ID
    assert obj.token == conftest.MOCK_TRACK_TOKEN

    assert obj.uri == track_uri.uri


def test_track_uri_is_ad(playlist_item_mock, ad_item_mock):
    track_uri = TrackUri._from_track(ad_item_mock)
    obj = PandoraUri._from_uri(track_uri.uri)

    assert type(obj) is AdItemUri

    track_uri = TrackUri._from_track(playlist_item_mock)
    obj = PandoraUri._from_uri(track_uri.uri)

    assert type(obj) is not AdItemUri
