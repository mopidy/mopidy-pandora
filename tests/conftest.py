from __future__ import unicode_literals

import json

from mock import Mock

from pandora.models.pandora import Playlist, PlaylistItem, Station, StationList

import pytest

import requests

from mopidy_pandora import backend

MOCK_STATION_SCHEME = "station"
MOCK_STATION_NAME = "Mock Station"
MOCK_STATION_ID = "0000000000000000001"
MOCK_STATION_TOKEN = "0000000000000000010"
MOCK_STATION_DETAIL_URL = " http://mockup.com/station/detail_url?..."
MOCK_STATION_ART_URL = " http://mockup.com/station/art_url?..."

MOCK_STATION_LIST_CHECKSUM = "aa00aa00aa00aa00aa00aa00aa00aa00"

MOCK_TRACK_SCHEME = "track"
MOCK_TRACK_NAME = "Mock Track"
MOCK_TRACK_TOKEN = "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001"
MOCK_TRACK_AUDIO_HIGH = "http://mockup.com/high_quality_audiofile.mp4?..."
MOCK_TRACK_AUDIO_MED = "http://mockup.com/medium_quality_audiofile.mp4?..."
MOCK_TRACK_AUDIO_LOW = "http://mockup.com/low_quality_audiofile.mp4?..."
MOCK_TRACK_DETAIL_URL = " http://mockup.com/track/detail_url?..."
MOCK_TRACK_ART_URL = " http://mockup.com/track/art_url?..."
MOCK_TRACK_INDEX = "1"

MOCK_DEFAULT_AUDIO_QUALITY = "highQuality"


@pytest.fixture(scope="session")
def config():
    return {
        'http': {
            'hostname': '127.0.0.1',
            'port': '6680'
        },
        'pandora': {
            'api_host': 'test_host',
            'partner_encryption_key': 'test_encryption_key',
            'partner_decryption_key': 'test_decryption_key',
            'partner_username': 'partner_name',
            'partner_password': 'partner_password',
            'partner_device': 'test_device',
            'username': 'john',
            'password': 'doe',
            'preferred_audio_quality': MOCK_DEFAULT_AUDIO_QUALITY,
            'sort_order': 'date',
            'auto_setup': True,

            'event_support_enabled': True,
            'double_click_interval': '0.1',
            'on_pause_resume_click': 'thumbs_up',
            'on_pause_next_click': 'thumbs_down',
            'on_pause_previous_click': 'sleep',
        }
    }


def get_backend(config, simulate_request_exceptions=False):
    obj = backend.PandoraBackend(config=config, audio=Mock())

    obj.rpc_client._do_rpc = rpc_call_not_implemented_mock

    if simulate_request_exceptions:
        type(obj.api.transport).__call__ = request_exception_mock
    else:
        # Ensure that we never do an actual call to the Pandora server while
        # running tests
        type(obj.api.transport).__call__ = transport_call_not_implemented_mock

    obj._event_loop = Mock()
    return obj


@pytest.fixture(scope="session")
def station_result_mock():
    mock_result = {"stat": "ok",
                   "result":
                       {"stationId": MOCK_STATION_ID,
                        "stationDetailUrl": MOCK_STATION_DETAIL_URL,
                        "artUrl": MOCK_STATION_ART_URL,
                        "stationToken": MOCK_STATION_TOKEN,
                        "stationName": MOCK_STATION_NAME},
                   }

    return mock_result


@pytest.fixture(scope="session")
def station_mock(simulate_request_exceptions=False):
    return Station.from_json(get_backend(config(), simulate_request_exceptions).api, station_result_mock()["result"])


@pytest.fixture(scope="session")
def get_station_mock(self, station_token):
    return station_mock()


@pytest.fixture(scope="session")
def playlist_result_mock():
    # TODO: Test inclusion of add tokens
    mock_result = {"stat": "ok",
                   "result": {
                       "items": [{
                                 "trackToken": MOCK_TRACK_TOKEN,
                                 "artistName": "Mock Artist Name",
                                 "albumName": "Mock Album Name",
                                 "albumArtUrl": MOCK_TRACK_ART_URL,
                                 "audioUrlMap": {
                                     "highQuality": {
                                         "bitrate": "64",
                                         "encoding": "aacplus",
                                         "audioUrl": MOCK_TRACK_AUDIO_HIGH,
                                         "protocol": "http"
                                     },
                                     "mediumQuality": {
                                         "bitrate": "64",
                                         "encoding": "aacplus",
                                         "audioUrl": MOCK_TRACK_AUDIO_MED,
                                         "protocol": "http"
                                     },
                                     "lowQuality": {
                                         "bitrate": "32",
                                         "encoding": "aacplus",
                                         "audioUrl": MOCK_TRACK_AUDIO_LOW,
                                         "protocol": "http"
                                     }
                                 },
                                 "songName": MOCK_TRACK_NAME,
                                 "songDetailUrl": MOCK_TRACK_DETAIL_URL,
                                 "stationId": MOCK_STATION_ID,
                                 "songRating": 0, }]}}

    return mock_result


@pytest.fixture(scope="session")
def playlist_mock(simulate_request_exceptions=False):
    return Playlist.from_json(get_backend(config(), simulate_request_exceptions).api, playlist_result_mock()["result"])


@pytest.fixture(scope="session")
def get_playlist_mock(self, station_token):
    return playlist_mock()


@pytest.fixture(scope="session")
def get_station_playlist_mock(self):
    return iter(get_playlist_mock(self, MOCK_STATION_TOKEN))


@pytest.fixture(scope="session")
def playlist_item_mock():
    return PlaylistItem.from_json(get_backend(
        config()).api, playlist_result_mock()["result"]["items"][0])


@pytest.fixture(scope="session")
def station_list_result_mock():
    mock_result = {"stat": "ok",
                   "result": {"stations": [
                       {"stationId": MOCK_STATION_ID.replace("1", "2"), "stationToken": MOCK_STATION_TOKEN,
                        "stationName": MOCK_STATION_NAME + " 2"},
                       {"stationId": MOCK_STATION_ID,
                        "stationToken": MOCK_STATION_TOKEN,
                        "stationName": MOCK_STATION_NAME + " 1"}, ], "checksum": MOCK_STATION_LIST_CHECKSUM}
                   }

    return mock_result["result"]


@pytest.fixture
def get_station_list_mock(self):
    return StationList.from_json(get_backend(config()).api, station_list_result_mock())


@pytest.fixture(scope="session")
def request_exception_mock(self, *args, **kwargs):
    raise requests.exceptions.RequestException


@pytest.fixture
def transport_call_not_implemented_mock(self, method, **data):
    raise TransportCallTestNotImplemented(method + "(" + json.dumps(self.remove_empty_values(data)) + ")")


class TransportCallTestNotImplemented(Exception):
    pass


@pytest.fixture
def rpc_call_not_implemented_mock(method, params=None):
    raise RPCCallTestNotImplemented(method + "(" + params + ")")


class RPCCallTestNotImplemented(Exception):
    pass
