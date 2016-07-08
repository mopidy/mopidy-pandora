from __future__ import absolute_import, division, print_function, unicode_literals

import json
import threading

import mock

from pandora import APIClient

from pandora.models.pandora import AdItem, GenreStation, GenreStationList, PlaylistItem, SearchResult, \
    SearchResultItem, Station, StationList

import pytest

import requests

from mopidy_pandora import backend

MOCK_STATION_TYPE = 'station'
MOCK_STATION_NAME = 'Mock Station'
MOCK_STATION_ID = '0000000000000000001'
MOCK_STATION_TOKEN = '0000000000000000001'
MOCK_STATION_DETAIL_URL = 'http://mockup.com/station/detail_url?...'
MOCK_STATION_ART_URL = 'http://mockup.com/station/art_url?...'

MOCK_STATION_LIST_CHECKSUM = 'aa00aa00aa00aa00aa00aa00aa00aa00'

MOCK_TRACK_TYPE = 'track'
MOCK_TRACK_NAME = 'Mock Track'
MOCK_TRACK_TOKEN = '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001'
MOCK_TRACK_AD_TOKEN = '000000000000000000-none'
MOCK_TRACK_AUDIO_HIGH = 'http://mockup.com/high_quality_audiofile.mp4?...'
MOCK_TRACK_AUDIO_MED = 'http://mockup.com/medium_quality_audiofile.mp4?...'
MOCK_TRACK_AUDIO_LOW = 'http://mockup.com/low_quality_audiofile.mp4?...'
MOCK_TRACK_DETAIL_URL = 'http://mockup.com/track/detail_url?...'
MOCK_TRACK_ART_URL = 'http://mockup.com/track/art_url?...'
MOCK_TRACK_INDEX = '1'

MOCK_DEFAULT_AUDIO_QUALITY = 'highQuality'

MOCK_AD_TYPE = 'ad'


@pytest.fixture
def config():
    return {
        'http': {
            'hostname': '127.0.0.1',
            'port': '6680'
        },
        'proxy': {
            'hostname': 'host_mock',
            'port': 'port_mock'
        },
        'pandora': {
            'enabled': True,
            'api_host': 'test_host',
            'partner_encryption_key': 'test_encryption_key',
            'partner_decryption_key': 'test_decryption_key',
            'partner_username': 'partner_name',
            'partner_password': 'partner_password',
            'partner_device': 'test_device',
            'username': 'john',
            'password': 'smith',
            'preferred_audio_quality': MOCK_DEFAULT_AUDIO_QUALITY,
            'sort_order': 'a-z',
            'auto_setup': True,
            'cache_time_to_live': 86400,

            'event_support_enabled': True,
            'double_click_interval': '0.5',
            'on_pause_resume_click': 'thumbs_up',
            'on_pause_next_click': 'thumbs_down',
            'on_pause_previous_click': 'sleep',
            'on_pause_resume_pause_click': 'delete_station',
        }
    }


def get_backend(config, simulate_request_exceptions=False):
    obj = backend.PandoraBackend(config=config, audio=mock.Mock())

    if simulate_request_exceptions:
        type(obj.api.transport).__call__ = request_exception_mock
    else:
        # Ensure that we never do an actual call to the Pandora server while
        # running tests
        type(obj.api.transport).__call__ = transport_call_not_implemented_mock

    obj._event_loop = mock.Mock()
    return obj


@pytest.fixture(scope='session')
def genre_station_mock(simulate_request_exceptions=False):
    return GenreStation.from_json(get_backend(config(), simulate_request_exceptions).api,
                                  genre_stations_result_mock()['categories'][0]['stations'][0])


@pytest.fixture(scope='session')
def station_result_mock():
    mock_result = {'stat': 'ok',
                   'result':
                       {'stationId': MOCK_STATION_ID,
                        'stationDetailUrl': MOCK_STATION_DETAIL_URL,
                        'artUrl': MOCK_STATION_ART_URL,
                        'stationToken': MOCK_STATION_TOKEN,
                        'stationName': MOCK_STATION_NAME},
                   }

    return mock_result


@pytest.fixture(scope='session')
def station_mock(simulate_request_exceptions=False):
    return Station.from_json(get_backend(config(), simulate_request_exceptions).api,
                             station_result_mock()['result'])


@pytest.fixture(scope='session')
def get_station_mock(self, station_token):
    return station_mock()


@pytest.fixture(scope='session')
def playlist_result_mock():
    mock_result = {'stat': 'ok',
                   'result': dict(items=[{
                       'trackToken': MOCK_TRACK_TOKEN,
                       'artistName': 'Mock Artist Name',
                       'albumName': 'Mock Album Name',
                       'albumArtUrl': MOCK_TRACK_ART_URL,
                       'audioUrlMap': {
                           'highQuality': {
                               'bitrate': '64',
                               'encoding': 'aacplus',
                               'audioUrl': MOCK_TRACK_AUDIO_HIGH,
                               'protocol': 'http'
                           },
                           'mediumQuality': {
                               'bitrate': '64',
                               'encoding': 'aacplus',
                               'audioUrl': MOCK_TRACK_AUDIO_MED,
                               'protocol': 'http'
                           },
                           'lowQuality': {
                               'bitrate': '32',
                               'encoding': 'aacplus',
                               'audioUrl': MOCK_TRACK_AUDIO_LOW,
                               'protocol': 'http'
                           }
                       },
                       'trackLength': 0,
                       'songName': MOCK_TRACK_NAME,
                       'songDetailUrl': MOCK_TRACK_DETAIL_URL,
                       'stationId': MOCK_STATION_ID,
                       'songRating': 0,
                       'adToken': None, },

                       # Also add an advertisement to the playlist.
                       {
                           'adToken': MOCK_TRACK_AD_TOKEN
                       },
                   ])}

    return mock_result


@pytest.fixture(scope='session')
def ad_metadata_result_mock():
    mock_result = {'stat': 'ok',
                   'result': dict(title=MOCK_TRACK_NAME,
                                  companyName='Mock Company Name',
                                  clickThroughUrl='click_url_mock',
                                  imageUrl='img_url_mock',
                                  trackGain='0.0',
                                  audioUrlMap={
                                      'highQuality': {
                                          'bitrate': '64',
                                          'encoding': 'aacplus',
                                          'audioUrl': MOCK_TRACK_AUDIO_HIGH,
                                          'protocol': 'http'
                                      },
                                      'mediumQuality': {
                                          'bitrate': '64',
                                          'encoding': 'aacplus',
                                          'audioUrl': MOCK_TRACK_AUDIO_MED,
                                          'protocol': 'http'
                                      },
                                      'lowQuality': {
                                          'bitrate': '32',
                                          'encoding': 'aacplus',
                                          'audioUrl': MOCK_TRACK_AUDIO_LOW,
                                          'protocol': 'http'
                                      }
                                  },
                                  adTrackingTokens={
                                      MOCK_TRACK_AD_TOKEN
                                  }
                                  )
                   }

    return mock_result


@pytest.fixture(scope='session')
def playlist_mock(simulate_request_exceptions=False):
    with mock.patch.object(APIClient, '__call__', mock.Mock()) as call_mock:
        call_mock.return_value = playlist_result_mock()['result']
        return get_backend(config(), simulate_request_exceptions).api.get_playlist(MOCK_STATION_TOKEN)


@pytest.fixture(scope='session')
def get_playlist_mock(self, station_token):
    return playlist_mock()


@pytest.fixture(scope='session')
def get_station_playlist_mock(self):
    return iter(get_playlist_mock(self, MOCK_STATION_TOKEN))


@pytest.fixture
def playlist_item_mock():
    return PlaylistItem.from_json(get_backend(
        config()).api, playlist_result_mock()['result']['items'][0])


@pytest.fixture
def ad_item_mock():
    ad_item = AdItem.from_json(get_backend(
        config()).api, ad_metadata_result_mock()['result'])
    ad_item.station_id = MOCK_STATION_ID
    ad_item.ad_token = MOCK_TRACK_AD_TOKEN
    return ad_item


@pytest.fixture
def get_ad_item_mock(self, token):
    return ad_item_mock()


@pytest.fixture(scope='session')
def genre_stations_result_mock():
    mock_result = {'stat': 'ok',
                   'result': {
                       'categories': [{
                           'stations': [{
                               'stationToken': 'G100',
                               'stationName': 'Genre mock',
                               'stationId': 'G100'
                           }],
                           'categoryName': 'Category mock'
                       }],
                   }}

    return mock_result['result']


@pytest.fixture(scope='session')
def station_list_result_mock():
    quickmix_station_id = MOCK_STATION_ID.replace('1', '2')
    mock_result = {'stat': 'ok',
                   'result': {'stations': [
                       {'stationId': quickmix_station_id,
                        'stationToken': MOCK_STATION_TOKEN.replace('1', '2'),
                        'stationName': MOCK_STATION_NAME + ' 2'},
                       {'stationId': MOCK_STATION_ID,
                        'stationToken': MOCK_STATION_TOKEN,
                        'stationName': MOCK_STATION_NAME + ' 1'},
                       {'stationId': MOCK_STATION_ID.replace('1', '3'),
                        'stationToken': MOCK_STATION_TOKEN.replace('1', '3'),
                        'stationName': 'QuickMix', 'isQuickMix': True,
                        'quickMixStationIds': [quickmix_station_id]},
                   ], 'checksum': MOCK_STATION_LIST_CHECKSUM},
                   }

    return mock_result['result']


@pytest.fixture(scope='session')
def search_result_mock():
    mock_result = {'stat': 'ok',
                   'result': {'nearMatchesAvailable': True,
                              'explanation': '',
                              'songs': [{
                                  'artistName': 'search_song_artist_mock',
                                  'musicToken': 'S1234567',
                                  'songName': MOCK_TRACK_NAME,
                                  'score': 100
                              }],
                              'artists': [
                                  {
                                      'artistName': 'search_artist_artist_mock',
                                      'musicToken': 'R123456',
                                      'likelyMatch': False,
                                      'score': 100
                                  },
                                  {
                                      'artistName': 'search_artist_composer_mock',
                                      'musicToken': 'C123456',
                                      'likelyMatch': False,
                                      'score': 100
                                  },
                              ],
                              'genreStations': [{
                                  'musicToken': 'G123',
                                  'score': 100,
                                  'stationName': 'search_genre_mock'
                              }]}
                   }

    return mock_result['result']


@pytest.fixture
def get_station_list_mock(self, force_refresh=False):
    return StationList.from_json(get_backend(config()).api, station_list_result_mock())


@pytest.fixture
def get_genre_stations_mock(self, force_refresh=False):
    return GenreStationList.from_json(get_backend(config()).api, genre_stations_result_mock())


@pytest.fixture(scope='session')
def request_exception_mock(self, *args, **kwargs):
    raise requests.exceptions.RequestException


@pytest.fixture
def transport_call_not_implemented_mock(self, method, **data):
    raise TransportCallTestNotImplemented(method + '(' + json.dumps(self.remove_empty_values(data)) + ')')


@pytest.fixture
def search_item_mock():
    return SearchResultItem.from_json(get_backend(
        config()).api, search_result_mock()['genreStations'][0])


@pytest.fixture
def search_mock(self, search_text, include_near_matches=False, include_genre_stations=False):
    return SearchResult.from_json(get_backend(config()).api, search_result_mock())


class TransportCallTestNotImplemented(Exception):
    pass


# Based on https://pypi.python.org/pypi/tl.testing/0.5
# Copyright (c) 2011-2012 Thomas Lotze
class ThreadJoiner(object):
    """Context manager that tries to join any threads started by its suite.

    This context manager is instantiated with a mandatory ``timeout``
    parameter and an optional ``check_alive`` switch. The time-out is applied
    when joining each of the new threads started while executing the context
    manager's code suite. If ``check_alive`` has a true value (the default),
    a ``RuntimeError`` is raised if a thread is still alive after the attempt
    to join timed out.

    Returns an instance of itself upon entering. This instance has a
    ``before`` attribute that is a collection of all threads active when the
    manager was entered. After the manager exited, the instance has another
    attribute, ``left_behind``, that is a collection of any threads that could
    not be joined within the time-out period. The latter is obviously only
    useful if ``check_alive`` is set to a false value.

    """

    def __init__(self, timeout, check_alive=True):
        self.timeout = timeout
        self.check_alive = check_alive

    def __enter__(self):
        self.before = set(threading.enumerate())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for thread in set(threading.enumerate()) - self.before:
            thread.join(self.timeout)
            if self.check_alive and thread.is_alive():
                raise RuntimeError('Timeout joining thread %r' % thread)
        self.left_behind = sorted(
            set(threading.enumerate()) - self.before, key=lambda t: t.name)

    def wait(self, timeout):
        for thread in set(threading.enumerate()) - self.before:
            thread.join(timeout)
