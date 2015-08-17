# coding=utf-8
from __future__ import unicode_literals

import conftest

import pytest

from mopidy_pandora.uri import PandoraUri, StationUri, TrackUri


def test_pandora_parse_mock_uri():

    uri = "pandora:mock"

    obj = PandoraUri.parse(uri)

    assert isinstance(obj, PandoraUri)
    assert obj.uri == uri


def test_pandora_parse_unicode_mock_uri():

    uri = PandoraUri("pandora:Ω≈ç√∫˜µ≤≥÷")

    obj = PandoraUri.parse(uri.uri)

    assert isinstance(obj, PandoraUri)
    assert obj.uri == uri.uri


def test_pandora_parse_int_mock_uri():

    uri = PandoraUri(1)

    obj = PandoraUri.parse(uri.uri)

    assert isinstance(obj, PandoraUri)
    assert obj.uri == uri.uri


def test_pandora_parse_none_mock_uri():

    uri = PandoraUri()

    assert uri.quote(None) == ''


def test_pandora_parse_invalid_mock_uri():
    with pytest.raises(IndexError):

        PandoraUri().parse('invalid')


def test_station_uri_from_station(station_mock):

    station_uri = StationUri.from_station(station_mock)

    assert station_uri.uri == "pandora:" + \
        station_uri.quote(conftest.MOCK_STATION_SCHEME) + ":" + \
        station_uri.quote(conftest.MOCK_STATION_ID) + ":" + \
        station_uri.quote(conftest.MOCK_STATION_TOKEN) + ":" + \
        station_uri.quote(conftest.MOCK_STATION_NAME) + ":" + \
        station_uri.quote(conftest.MOCK_STATION_DETAIL_URL) + ":" + \
        station_uri.quote(conftest.MOCK_STATION_ART_URL)


def test_station_uri_parse(station_mock):

    station_uri = StationUri.from_station(station_mock)

    obj = StationUri.parse(station_uri.uri)

    assert isinstance(obj, StationUri)

    assert obj.scheme == conftest.MOCK_STATION_SCHEME
    assert obj.station_id == conftest.MOCK_STATION_ID
    assert obj.token == conftest.MOCK_STATION_TOKEN
    assert obj.name == conftest.MOCK_STATION_NAME
    assert obj.detail_url == conftest.MOCK_STATION_DETAIL_URL
    assert obj.art_url == conftest.MOCK_STATION_ART_URL

    assert obj.uri == station_uri.uri


def test_track_uri_from_track(playlist_item_mock):

    track_uri = TrackUri.from_track(playlist_item_mock)

    assert track_uri.uri == "pandora:" + \
        track_uri.quote(conftest.MOCK_TRACK_SCHEME) + ":" + \
        track_uri.quote(conftest.MOCK_STATION_ID) + ":" + \
        track_uri.quote(conftest.MOCK_TRACK_TOKEN) + ":" + \
        track_uri.quote(conftest.MOCK_TRACK_NAME) + ":" + \
        track_uri.quote(conftest.MOCK_TRACK_DETAIL_URL) + ":" + \
        track_uri.quote(conftest.MOCK_TRACK_ART_URL) + ":" + \
        track_uri.quote(conftest.MOCK_TRACK_AUDIO_HIGH) + ":" + \
        track_uri.quote(0)


def test_track_uri_parse(playlist_item_mock):

    track_uri = TrackUri.from_track(playlist_item_mock)

    obj = TrackUri.parse(track_uri.uri)

    assert isinstance(obj, TrackUri)

    assert obj.scheme == conftest.MOCK_TRACK_SCHEME
    assert obj.station_id == conftest.MOCK_STATION_ID
    assert obj.token == conftest.MOCK_TRACK_TOKEN
    assert obj.name == conftest.MOCK_TRACK_NAME
    assert obj.detail_url == conftest.MOCK_TRACK_DETAIL_URL
    assert obj.art_url == conftest.MOCK_TRACK_ART_URL
    assert obj.audio_url == conftest.MOCK_TRACK_AUDIO_HIGH

    assert obj.uri == track_uri.uri
