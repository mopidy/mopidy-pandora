from __future__ import absolute_import, division, print_function, unicode_literals

import time

import mock

from mopidy import models

from pandora import APIClient
from pandora.models.pandora import Station, StationList

import pytest

from mopidy_pandora.client import MopidyAPIClient
from mopidy_pandora.library import PandoraLibraryProvider, StationCacheItem, TrackCacheItem

from mopidy_pandora.uri import GenreUri, PandoraUri, PlaylistItemUri, StationUri

from . import conftest


def test_get_images_for_ad_without_images(config, ad_item_mock):
    backend = conftest.get_backend(config)

    ad_uri = PandoraUri.factory('pandora:ad:{}:{}'.format(conftest.MOCK_STATION_ID, conftest.MOCK_TRACK_AD_TOKEN))
    ad_item_mock.image_url = None
    backend.library.pandora_track_cache[ad_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track), ad_item_mock)
    results = backend.library.get_images([ad_uri.uri])
    assert len(results[ad_uri.uri]) == 0


def test_get_images_for_ad_with_images(config, ad_item_mock):
    backend = conftest.get_backend(config)

    ad_uri = PandoraUri.factory('pandora:ad:{}:{}'.format(conftest.MOCK_STATION_ID, conftest.MOCK_TRACK_AD_TOKEN))
    backend.library.pandora_track_cache[ad_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track), ad_item_mock)
    results = backend.library.get_images([ad_uri.uri])
    assert len(results[ad_uri.uri]) == 1
    assert results[ad_uri.uri][0].uri == ad_item_mock.image_url


def test_get_images_for_unknown_uri_returns_empty_list(config, caplog):
    backend = conftest.get_backend(config)

    track_uri = PandoraUri.factory('pandora:track:mock_id:mock_token')
    results = backend.library.get_images([track_uri.uri])
    assert len(results[track_uri.uri]) == 0
    assert "Failed to lookup image for Pandora URI '{}'.".format(track_uri.uri) in caplog.text()


def test_get_images_for_unsupported_uri_type_issues_warning(config, caplog):
    backend = conftest.get_backend(config)

    search_uri = PandoraUri.factory('pandora:search:R12345')
    results = backend.library.get_images([search_uri.uri])
    assert len(results[search_uri.uri]) == 0
    assert "No images available for Pandora URIs of type 'search'.".format(search_uri.uri) in caplog.text()


def test_get_images_for_track_without_images(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    track_uri = PandoraUri.factory('pandora:track:mock_id:mock_token')
    playlist_item_mock.album_art_url = None
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                        playlist_item_mock)
    results = backend.library.get_images([track_uri.uri])
    assert len(results[track_uri.uri]) == 0


def test_get_images_for_track_with_images(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    track_uri = PandoraUri.factory('pandora:track:mock_id:mock_token')
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                        playlist_item_mock)
    results = backend.library.get_images([track_uri.uri])
    assert len(results[track_uri.uri]) == 1
    assert results[track_uri.uri][0].uri == playlist_item_mock.album_art_url


def test_get_next_pandora_track_fetches_track(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    station_mock = mock.Mock(spec=Station)
    station_mock.id = 'id_token_mock'
    backend.library.pandora_station_cache[station_mock.id] = StationCacheItem(station_mock, iter([playlist_item_mock]))

    ref = backend.library.get_next_pandora_track('id_token_mock')
    assert ref.uri == PandoraUri.factory(playlist_item_mock).uri
    assert backend.library.pandora_track_cache[ref.uri].ref == ref
    assert backend.library.pandora_track_cache[ref.uri].track == playlist_item_mock


def test_get_next_pandora_track_handles_no_more_tracks_available(config, caplog):
    backend = conftest.get_backend(config)

    station_mock = mock.Mock(spec=Station)
    station_mock.id = 'id_token_mock'
    backend.library.pandora_station_cache[station_mock.id] = StationCacheItem(station_mock, iter([]))

    track = backend.library.get_next_pandora_track('id_token_mock')
    assert track is None
    assert 'Error retrieving next Pandora track.' in caplog.text()


def test_get_next_pandora_track_renames_advertisements(config, station_mock):
    with mock.patch.object(MopidyAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', mock.Mock()) as get_playlist_mock:

            backend = conftest.get_backend(config)

            playlist = conftest.playlist_mock()
            playlist.pop(0)
            get_playlist_mock.return_value = iter(playlist)

            track = backend.library.get_next_pandora_track(station_mock.id)
            assert track.name == 'Advertisement'


def test_lookup_of_invalid_uri(config):
    with pytest.raises(NotImplementedError):
        backend = conftest.get_backend(config)

        backend.library.lookup('pandora:invalid')


def test_lookup_of_invalid_uri_type(config, caplog):
    with pytest.raises(ValueError):
        backend = conftest.get_backend(config)

        backend.library.lookup('pandora:station:mock_id:mock_token')
        assert 'Unexpected type to perform Pandora track lookup: station.' in caplog.text()


def test_lookup_of_ad_uri(config, ad_item_mock):
    backend = conftest.get_backend(config)

    track_uri = PlaylistItemUri._from_track(ad_item_mock)
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track), ad_item_mock)

    results = backend.library.lookup(track_uri.uri)
    assert len(results) == 1

    track = results[0]
    assert track.uri == track_uri.uri


def test_lookup_of_ad_uri_defaults_missing_values(config, ad_item_mock):
    backend = conftest.get_backend(config)

    ad_item_mock.title = ''
    ad_item_mock.company_name = None

    track_uri = PlaylistItemUri._from_track(ad_item_mock)
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track), ad_item_mock)

    results = backend.library.lookup(track_uri.uri)
    assert len(results) == 1

    track = results[0]
    assert track.name == 'Advertisement'
    assert '(Title not specified)' in next(iter(track.artists)).name
    assert track.album.name == '(Company name not specified)'


def test_lookup_of_search_uri(config, playlist_item_mock):
    with mock.patch.object(MopidyAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(APIClient, 'create_station',
                               mock.Mock(return_value=conftest.station_result_mock()['result'])) as create_station_mock:
            with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):

                backend = conftest.get_backend(config)

                station_mock = mock.Mock(spec=Station)
                station_mock.id = conftest.MOCK_STATION_ID
                backend.library.pandora_station_cache[station_mock.id] = \
                    StationCacheItem(conftest.station_result_mock()['result'],
                                     iter([playlist_item_mock]))

                track_uri = PlaylistItemUri._from_track(playlist_item_mock)
                backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                                    playlist_item_mock)

                results = backend.library.lookup("pandora:search:S1234567")
                # Make sure a station is created for the search URI first
                assert create_station_mock.called
                # Check that the first track to be played is returned correctly.
                assert results[0].uri == track_uri.uri


def test_lookup_of_track_uri(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    track_uri = PlaylistItemUri._from_track(playlist_item_mock)
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                        playlist_item_mock)

    results = backend.library.lookup(track_uri.uri)
    assert len(results) == 1

    track = results[0]
    assert track.uri == track_uri.uri


# Regression test for https://github.com/rectalogic/mopidy-pandora/issues/48
def test_lookup_of_track_that_does_not_specify_bitrate(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    playlist_item_mock.bitrate = None
    track_uri = PlaylistItemUri._from_track(playlist_item_mock)
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                        playlist_item_mock)

    results = backend.library.lookup(track_uri.uri)
    assert len(results) == 1

    track = results[0]
    assert track.uri == track_uri.uri


def test_lookup_of_missing_track(config, playlist_item_mock, caplog):
    backend = conftest.get_backend(config)

    track_uri = PandoraUri.factory(playlist_item_mock)
    results = backend.library.lookup(track_uri.uri)

    assert len(results) == 0
    assert "Failed to lookup Pandora URI '{}'.".format(track_uri.uri) in caplog.text()


def test_lookup_overrides_album_and_artist_uris(config, playlist_item_mock):
    backend = conftest.get_backend(config)

    track_uri = PlaylistItemUri._from_track(playlist_item_mock)
    backend.library.pandora_track_cache[track_uri.uri] = TrackCacheItem(mock.Mock(spec=models.Ref.track),
                                                                        playlist_item_mock)

    results = backend.library.lookup(track_uri.uri)
    track = results[0]
    assert next(iter(track.artists)).uri == track_uri.uri
    assert track.album.uri == track_uri.uri


def test_browse_directory_uri(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):

        backend = conftest.get_backend(config)
        results = backend.library.browse(backend.library.root_directory.uri)

        assert len(results) == 4

        assert results[0].type == models.Ref.DIRECTORY
        assert results[0].uri == PandoraUri('genres').uri

        assert results[1].type == models.Ref.DIRECTORY
        assert results[1].name.startswith('QuickMix')
        assert results[1].uri == StationUri._from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][2])).uri

        assert results[2].type == models.Ref.DIRECTORY
        assert results[2].uri == StationUri._from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][1])).uri

        assert results[3].type == models.Ref.DIRECTORY
        assert results[3].uri == StationUri._from_station(
            Station.from_json(backend.api, conftest.station_list_result_mock()['stations'][0])).uri


def test_browse_directory_marks_quickmix_stations(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):

        quickmix_station_uri = 'pandora:track:{}:{}'.format(conftest.MOCK_STATION_ID.replace('1', '2'),
                                                            conftest.MOCK_STATION_TOKEN.replace('1', '2'),)

        backend = conftest.get_backend(config)
        results = backend.library.browse(backend.library.root_directory.uri)

        for result in results:
            if result.uri == quickmix_station_uri:
                assert result.name.endswith('*')


def test_browse_directory_sort_za(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):

        config['pandora']['sort_order'] = 'A-Z'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == PandoraLibraryProvider.GENRE_DIR_NAME
        assert results[1].name.startswith('QuickMix')
        assert results[2].name == conftest.MOCK_STATION_NAME + ' 1'
        assert results[3].name == conftest.MOCK_STATION_NAME + ' 2' + '*'


def test_browse_directory_sort_date(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):

        config['pandora']['sort_order'] = 'date'
        backend = conftest.get_backend(config)

        results = backend.library.browse(backend.library.root_directory.uri)

        assert results[0].name == PandoraLibraryProvider.GENRE_DIR_NAME
        assert results[1].name.startswith('QuickMix')
        assert results[2].name == conftest.MOCK_STATION_NAME + ' 2' + '*'
        assert results[3].name == conftest.MOCK_STATION_NAME + ' 1'


def test_browse_genres(config):
    with mock.patch.object(MopidyAPIClient, 'get_genre_stations', conftest.get_genre_stations_mock):

        backend = conftest.get_backend(config)
        results = backend.library.browse(backend.library.genre_directory.uri)
        assert len(results) == 1
        assert results[0].name == 'Category mock'


def test_browse_raises_exception_for_unsupported_uri_type(config):
    with pytest.raises(NotImplementedError):
        backend = conftest.get_backend(config)
        backend.library.browse('pandora:invalid_uri')


def test_browse_resets_skip_limits(config):
    with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
        backend = conftest.get_backend(config)
        backend.playback._consecutive_track_skips = 5
        backend.library.browse(backend.library.root_directory.uri)

        assert backend.playback._consecutive_track_skips == 0


def test_browse_genre_category(config):
    with mock.patch.object(MopidyAPIClient, 'get_genre_stations', conftest.get_genre_stations_mock):

        backend = conftest.get_backend(config)
        category_uri = 'pandora:genre:Category mock'
        results = backend.library.browse(category_uri)
        assert len(results) == 1
        assert results[0].name == 'Genre mock'


def test_browse_genre_station_uri(config, genre_station_mock):
    with mock.patch.object(MopidyAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(APIClient, 'create_station',
                               mock.Mock(return_value=conftest.station_result_mock()['result'])) as create_station_mock:
            with mock.patch.object(APIClient, 'get_station_list', conftest.get_station_list_mock):
                with mock.patch.object(MopidyAPIClient, 'get_genre_stations', conftest.get_genre_stations_mock):

                    backend = conftest.get_backend(config)
                    genre_uri = GenreUri._from_station(genre_station_mock)
                    t = time.time()
                    backend.api.station_list_cache[t] = mock.Mock(spec=StationList)

                    results = backend.library.browse(genre_uri.uri)
                    assert len(results) == 1
                    assert backend.api.station_list_cache.currsize == 1
                    assert t not in list(backend.api.station_list_cache)
                    assert create_station_mock.called


def test_browse_station_uri(config, station_mock):
    with mock.patch.object(MopidyAPIClient, 'get_station', conftest.get_station_mock):
        with mock.patch.object(Station, 'get_playlist', conftest.get_station_playlist_mock):

            backend = conftest.get_backend(config)
            station_uri = StationUri._from_station(station_mock)

            results = backend.library.browse(station_uri.uri)
            # Station should just contain the first track to be played.
            assert len(results) == 1


def test_formatted_search_query_concatenates_queries_into_free_text(config):
    backend = conftest.get_backend(config)

    result = backend.library._formatted_search_query({
        'any': ['any_mock'], 'artist': ['artist_mock'], 'track_name': ['track_mock']
    })
    assert 'any_mock' in result and 'artist_mock' in result and 'track_mock' in result


def test_formatted_search_query_ignores_unsupported_attributes(config):
    backend = conftest.get_backend(config)

    result = backend.library._formatted_search_query({'album': ['album_mock']})
    assert len(result) is 0


def test_refresh_without_uri_refreshes_root(config):
    backend = conftest.get_backend(config)
    backend.api.get_station_list = mock.Mock()
    backend.api.get_genre_stations = mock.Mock()

    backend.library.refresh()
    backend.api.get_station_list.assert_called_with(force_refresh=True)
    assert not backend.api.get_genre_stations.called


def test_refresh_root_directory(config):
    backend = conftest.get_backend(config)
    backend.api.get_station_list = mock.Mock()
    backend.api.get_genre_stations = mock.Mock()

    backend.library.refresh(backend.library.root_directory.uri)
    backend.api.get_station_list.assert_called_with(force_refresh=True)
    assert not backend.api.get_genre_stations.called


def test_refresh_genre_directory(config):
    backend = conftest.get_backend(config)
    backend.api.get_station_list = mock.Mock()
    backend.api.get_genre_stations = mock.Mock()

    backend.library.refresh(backend.library.genre_directory.uri)
    backend.api.get_genre_stations.assert_called_with(force_refresh=True)
    assert not backend.api.get_station_list.called


def test_refresh_station_directory_invalid_uri_type_raises_exception(config):
    with pytest.raises(ValueError):
        backend = conftest.get_backend(config)
        backend.api.get_station_list = mock.Mock()
        backend.api.get_genre_stations = mock.Mock()

        backend.library.refresh('pandora:track:id_token_mock:id_token_mock')


def test_refresh_station_directory(config):
    backend = conftest.get_backend(config)
    backend.api.get_station_list = mock.Mock()
    backend.api.get_genre_stations = mock.Mock()

    station_mock = mock.Mock(spec=Station)
    station_mock.id = 'id_token_mock'
    backend.library.pandora_station_cache[station_mock.id] = StationCacheItem(station_mock, iter([]))

    backend.library.refresh('pandora:station:id_token_mock:id_token_mock')
    assert backend.library.pandora_station_cache.currsize == 0
    assert not backend.api.get_station_list.called
    assert not backend.api.get_genre_stations.called


def test_refresh_station_directory_not_in_cache_handles_key_error(config):
    backend = conftest.get_backend(config)
    backend.api.get_station_list = mock.Mock()
    backend.api.get_genre_stations = mock.Mock()

    backend.library.refresh('pandora:station:id_token_mock:id_token_mock')
    assert backend.library.pandora_station_cache.currsize == 0
    assert not backend.api.get_station_list.called
    assert not backend.api.get_genre_stations.called


def test_search_returns_empty_result_for_unsupported_queries(config, caplog):
    backend = conftest.get_backend(config)
    assert len(backend.library.search({'album': ['album_name_mock']})) is 0
    assert 'Unsupported Pandora search query:' in caplog.text()


def test_search(config):
    with mock.patch.object(APIClient, 'search', conftest.search_mock):

        backend = conftest.get_backend(config)
        search_result = backend.library.search({'any': 'search_mock'})

        assert len(search_result.tracks) is 2
        assert search_result.tracks[0].uri == 'pandora:search:G123'
        assert search_result.tracks[0].name == 'search_genre_mock (Pandora genre)'

        assert search_result.tracks[1].uri == 'pandora:search:S1234567'
        assert search_result.tracks[1].name == conftest.MOCK_TRACK_NAME + ' (Pandora station)'

        assert len(search_result.artists) is 2
        assert search_result.artists[0].uri == 'pandora:search:R123456'
        assert search_result.artists[0].name == 'search_artist_artist_mock (Pandora artist)'

        assert search_result.artists[1].uri == 'pandora:search:C123456'
        assert search_result.artists[1].name == 'search_artist_composer_mock (Pandora composer)'
