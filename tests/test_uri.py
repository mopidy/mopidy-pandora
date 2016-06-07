# coding=utf-8
from __future__ import absolute_import, division, print_function, unicode_literals

from mock import mock

from mopidy import models

from pandora.models.pandora import GenreStation, Station

import pytest

from mopidy_pandora.uri import AdItemUri, GenreStationUri, GenreUri, PandoraUri, PlaylistItemUri, SearchUri,\
    StationUri, TrackUri

from . import conftest


def test_factory_unsupported_type():
    with pytest.raises(NotImplementedError):

        PandoraUri.factory(0)


def test_ad_uri_parse():
    mock_uri = 'pandora:ad:id_mock:ad_token_mock'
    obj = PandoraUri._from_uri(mock_uri)

    assert type(obj) is AdItemUri

    assert obj.uri_type == 'ad'
    assert obj.station_id == 'id_mock'
    assert obj.ad_token == 'ad_token_mock'

    assert obj.uri == mock_uri


def test_factory_ad(ad_item_mock):
    obj = PandoraUri.factory(ad_item_mock)

    assert type(obj) is AdItemUri
    assert obj.uri == 'pandora:ad:{}:{}'.format(conftest.MOCK_STATION_ID, conftest.MOCK_TRACK_AD_TOKEN)


def test_factory_playlist_item(playlist_item_mock):
    obj = PandoraUri.factory(playlist_item_mock)

    assert type(obj) is PlaylistItemUri
    assert obj.uri == 'pandora:track:{}:{}'.format(conftest.MOCK_STATION_ID, conftest.MOCK_TRACK_TOKEN)


def test_factory_track_ref():
    track_ref = models.Ref(name='name_mock', uri='pandora:track:station_id_mock:track_token_mock')

    obj = PandoraUri.factory(track_ref)

    assert type(obj) is PlaylistItemUri
    assert obj.uri == track_ref.uri


def test_factory_track():
    track = models.Track(name='name_mock', uri='pandora:track:station_id_mock:track_token_mock')

    obj = PandoraUri.factory(track)

    assert type(obj) is PlaylistItemUri
    assert obj.uri == track.uri


def test_factory_returns_correct_station_uri_types():
        station_mock = mock.PropertyMock(spec=GenreStation)
        station_mock.id = 'G100'
        station_mock.token = 'G100'
        assert type(PandoraUri.factory(station_mock)) is GenreStationUri

        station_mock = mock.PropertyMock(spec=Station)
        station_mock.id = 'id_mock'
        station_mock.token = 'token_mock'
        assert type(PandoraUri.factory(station_mock)) is StationUri


def test_pandora_parse_mock_uri():
    uri = 'pandora:station:id_mock:token_mock'
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
    uri = 'pandora:station:id_mock:'
    obj = PandoraUri._from_uri(uri)

    obj.token = 0
    assert obj.uri == uri + '0'


def test_pandora_parse_none_mock_uri():
    uri = PandoraUri()
    assert uri.encode(None) == ''


def test_pandora_parse_invalid_type_raises_exception():
    with pytest.raises(NotImplementedError):

        PandoraUri()._from_uri('pandora:invalid_uri')


def test_pandora_parse_invalid_scheme_raises_exception():
    with pytest.raises(NotImplementedError):

        PandoraUri()._from_uri('not_the_pandora_scheme:invalid')


def test_search_uri_parse():

    obj = PandoraUri._from_uri('pandora:search:S1234567')
    assert type(obj) is SearchUri

    assert obj.uri_type == SearchUri.uri_type
    assert obj.token == 'S1234567'

    obj = PandoraUri._from_uri('pandora:search:R123456')
    assert type(obj) is SearchUri

    assert obj.uri_type == SearchUri.uri_type
    assert obj.token == 'R123456'

    obj = PandoraUri._from_uri('pandora:search:C12345')
    assert type(obj) is SearchUri

    assert obj.uri_type == SearchUri.uri_type
    assert obj.token == 'C12345'

    obj = PandoraUri._from_uri('pandora:search:G123')
    assert type(obj) is SearchUri

    assert obj.uri_type == SearchUri.uri_type
    assert obj.token == 'G123'


def test_search_uri_is_track_search():
    obj = PandoraUri._from_uri('pandora:search:S1234567')
    assert obj.is_track_search

    obj.token = 'R123456'
    assert not obj.is_track_search


def test_search_uri_is_artist_search():
    obj = PandoraUri._from_uri('pandora:search:S1234567')
    assert not obj.is_artist_search

    obj.token = 'R123456'
    assert obj.is_artist_search


def test_search_uri_is_composer_search():
    obj = PandoraUri._from_uri('pandora:search:S1234567')
    assert not obj.is_composer_search

    obj.token = 'C12345'
    assert obj.is_composer_search


def test_search_uri_is_genre_search():
    obj = PandoraUri._from_uri('pandora:search:S1234567')
    assert not obj.is_genre_search

    obj.token = 'G123'
    assert obj.is_genre_search


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
    station_mock.id = 'G100'
    station_mock.token = 'G100'

    obj = StationUri._from_station(station_mock)

    assert type(obj) is GenreStationUri


def test_genre_uri_parse():
    mock_uri = 'pandora:genre:category_mock'
    obj = PandoraUri._from_uri(mock_uri)

    assert type(obj) is GenreUri

    assert obj.uri_type == 'genre'
    assert obj.category_name == 'category_mock'

    assert obj.uri == mock_uri


def test_genre_station_uri_parse():
    mock_uri = 'pandora:genre_station:G100:G100'
    obj = PandoraUri._from_uri(mock_uri)

    assert type(obj) is GenreStationUri

    assert obj.uri_type == 'genre_station'
    assert obj.station_id == 'G100'
    assert obj.token == 'G100'

    assert obj.uri == mock_uri


def test_genre_station_uri_from_station_returns_correct_type():
    genre_mock = mock.PropertyMock(spec=Station)
    genre_mock.id = 'id_mock'
    genre_mock.token = 'token_mock'

    obj = StationUri._from_station(genre_mock)

    assert type(obj) is StationUri

    assert obj.uri_type == 'station'
    assert obj.station_id == 'id_mock'
    assert obj.token == 'token_mock'

    assert obj.uri == 'pandora:station:id_mock:token_mock'


def test_genre_station_uri_from_genre_station_returns_correct_type():
    genre_station_mock = mock.PropertyMock(spec=GenreStation)
    genre_station_mock.id = 'G100'
    genre_station_mock.token = 'G100'

    obj = GenreStationUri._from_station(genre_station_mock)

    assert type(obj) is GenreStationUri

    assert obj.uri_type == 'genre_station'
    assert obj.station_id == 'G100'
    assert obj.token == 'G100'

    assert obj.uri == 'pandora:genre_station:G100:G100'


def test_track_uri_from_track(playlist_item_mock):
    track_uri = TrackUri._from_track(playlist_item_mock)

    assert track_uri.uri == '{}:{}:{}:{}'.format(PandoraUri.SCHEME,
                                                 track_uri.encode(conftest.MOCK_TRACK_TYPE),
                                                 track_uri.encode(conftest.MOCK_STATION_TOKEN),
                                                 track_uri.encode(conftest.MOCK_TRACK_TOKEN))


def test_track_uri_from_track_unsupported_type(playlist_result_mock):
    with pytest.raises(NotImplementedError):

        PandoraUri._from_track(playlist_result_mock)


def test_track_uri_from_track_for_ads(ad_item_mock):
    track_uri = TrackUri._from_track(ad_item_mock)

    assert track_uri.uri == '{}:{}:{}:{}'.format(PandoraUri.SCHEME,
                                                 track_uri.encode(conftest.MOCK_AD_TYPE),
                                                 conftest.MOCK_STATION_ID, conftest.MOCK_TRACK_AD_TOKEN)


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
