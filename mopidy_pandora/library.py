from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import re

from collections import namedtuple

from cachetools import LRUCache

from mopidy import backend, models

from pandora.models.pandora import Station

from pydora.utils import iterate_forever

from mopidy_pandora.uri import AdItemUri, GenreUri, PandoraUri, SearchUri, StationUri, TrackUri  # noqa I101

logger = logging.getLogger(__name__)

StationCacheItem = namedtuple('StationCacheItem', 'station, iter')
TrackCacheItem = namedtuple('TrackCacheItem', 'ref, track')


class PandoraLibraryProvider(backend.LibraryProvider):
    ROOT_DIR_NAME = 'Pandora'
    GENRE_DIR_NAME = 'Browse Genres'

    root_directory = models.Ref.directory(name=ROOT_DIR_NAME, uri=PandoraUri('directory').uri)
    genre_directory = models.Ref.directory(name=GENRE_DIR_NAME, uri=PandoraUri('genres').uri)

    def __init__(self, backend, sort_order):
        super(PandoraLibraryProvider, self).__init__(backend)
        self.sort_order = sort_order.lower()

        self.pandora_station_cache = LRUCache(maxsize=5, missing=self.get_station_cache_item)
        self.pandora_track_cache = LRUCache(maxsize=10)

    def browse(self, uri):
        self.backend.playback.reset_skip_limits()
        if uri == self.root_directory.uri:
            return self._browse_stations()

        if uri == self.genre_directory.uri:
            return self._browse_genre_categories()

        pandora_uri = PandoraUri.factory(uri)

        if isinstance(pandora_uri, GenreUri):
            return self._browse_genre_stations(uri)

        if isinstance(pandora_uri, StationUri):
            return self._browse_tracks(uri)

    def lookup(self, uri):
        pandora_uri = PandoraUri.factory(uri)
        if isinstance(pandora_uri, SearchUri):
            # Create the station first so that it can be browsed.
            station_uri = self._create_station_for_token(pandora_uri.token)
            track = self._browse_tracks(station_uri.uri)[0]

            # Recursive call to look up first track in station that was searched for.
            return self.lookup(track.uri)

        if isinstance(pandora_uri, TrackUri):
            try:
                track = self.lookup_pandora_track(uri)
            except KeyError:
                logger.exception("Failed to lookup Pandora URI '{}'.".format(uri))
                return []
            else:
                track_kwargs = {'uri': uri}
                (album_kwargs, artist_kwargs) = {}, {}
                # TODO: Album.images has been deprecated in Mopidy 1.2. Remove this code when all frontends have been
                #       updated to make use of the newer LibraryController.get_images()
                images = self.get_images([uri])[uri]
                if len(images) > 0:
                    album_kwargs = {'images': [image.uri for image in images]}

                if isinstance(pandora_uri, AdItemUri):
                    track_kwargs['name'] = 'Advertisement'

                    if not track.title:
                        track.title = '(Title not specified)'
                    artist_kwargs['name'] = track.title

                    if not track.company_name:
                        track.company_name = '(Company name not specified)'
                    album_kwargs['name'] = track.company_name
                else:
                    track_kwargs['name'] = track.song_name
                    track_kwargs['length'] = track.track_length * 1000
                    try:
                        track_kwargs['bitrate'] = int(track.bitrate)
                    except TypeError:
                        # Bitrate not specified for this stream, ignore.
                        pass
                    artist_kwargs['name'] = track.artist_name
                    album_kwargs['name'] = track.album_name
        else:
            raise ValueError('Unexpected type to perform Pandora track lookup: {}.'.format(pandora_uri.uri_type))

        artist_kwargs['uri'] = uri  # Artist lookups should just point back to the track itself.
        track_kwargs['artists'] = [models.Artist(**artist_kwargs)]
        album_kwargs['uri'] = uri   # Album lookups should just point back to the track itself.
        track_kwargs['album'] = models.Album(**album_kwargs)
        return [models.Track(**track_kwargs)]

    def get_images(self, uris):
        result = {}
        for uri in uris:
            image_uris = set()
            try:
                track = self.lookup_pandora_track(uri)
                if track.is_ad is True:
                    image_uri = track.image_url
                else:
                    image_uri = track.album_art_url
                if image_uri:
                    image_uris.update([image_uri])
            except (TypeError, KeyError):
                pandora_uri = PandoraUri.factory(uri)
                if isinstance(pandora_uri, TrackUri):
                    # Could not find the track as expected - exception.
                    logger.exception("Failed to lookup image for Pandora URI '{}'.".format(uri))
                else:
                    # Lookup
                    logger.warning("No images available for Pandora URIs of type '{}'.".format(pandora_uri.uri_type))
                pass
            result[uri] = [models.Image(uri=u) for u in image_uris]
        return result

    def _formatted_station_list(self, list):
        # Find QuickMix stations and move QuickMix to top
        for i, station in enumerate(list[:]):
            if station.is_quickmix:
                quickmix_stations = station.quickmix_stations
                if not station.name.endswith(' (marked with *)'):
                    station.name += ' (marked with *)'
                list.insert(0, list.pop(i))
                break

        # Mark QuickMix stations
        for station in list:
            if station.id in quickmix_stations:
                if not station.name.endswith('*'):
                    station.name += '*'

        return list

    def _browse_stations(self):
        station_directories = []

        stations = self.backend.api.get_station_list()
        if stations:
            if self.sort_order == 'a-z':
                stations.sort(key=lambda x: x.name, reverse=False)

            for station in self._formatted_station_list(stations):
                # As of version 5 of the Pandora API, station IDs and tokens are always equivalent.
                # We're using this assumption as we don't have the station token available for deleting the station.
                # Detect if any Pandora API changes ever breaks this assumption in the future.
                assert station.token == station.id
                station_directories.append(
                    models.Ref.directory(name=station.name, uri=PandoraUri.factory(station).uri))

        station_directories.insert(0, self.genre_directory)

        return station_directories

    def _browse_tracks(self, uri):
        pandora_uri = PandoraUri.factory(uri)
        return [self.get_next_pandora_track(pandora_uri.station_id)]

    def _create_station_for_token(self, token):
        json_result = self.backend.api.create_station(search_token=token)
        new_station = Station.from_json(self.backend.api, json_result)

        self.refresh()
        return PandoraUri.factory(new_station)

    def _browse_genre_categories(self):
        return [models.Ref.directory(name=category, uri=GenreUri(category).uri)
                for category in sorted(self.backend.api.get_genre_stations().keys())]

    def _browse_genre_stations(self, uri):
        return [models.Ref.directory(name=station.name, uri=PandoraUri.factory(station).uri)
                for station in self.backend.api.get_genre_stations()
                [PandoraUri.factory(uri).category_name]]

    def lookup_pandora_track(self, uri):
        return self.pandora_track_cache[uri].track

    def get_station_cache_item(self, station_id):
        if re.match('^([SRCG])', station_id):
            pandora_uri = self._create_station_for_token(station_id)
            station_id = pandora_uri.station_id

        station = self.backend.api.get_station(station_id)
        station_iter = iterate_forever(station.get_playlist)
        return StationCacheItem(station, station_iter)

    def get_next_pandora_track(self, station_id):
        try:
            station_iter = self.pandora_station_cache[station_id].iter
            track = next(station_iter)
        except Exception:
            logger.exception('Error retrieving next Pandora track.')
            return None

        track_uri = PandoraUri.factory(track)
        if isinstance(track_uri, AdItemUri):
            track_name = 'Advertisement'
        else:
            track_name = track.song_name

        ref = models.Ref.track(name=track_name, uri=track_uri.uri)
        self.pandora_track_cache[track_uri.uri] = TrackCacheItem(ref, track)
        return ref

    def refresh(self, uri=None):
        if not uri or uri == self.root_directory.uri:
            self.backend.api.get_station_list(force_refresh=True)
        elif uri == self.genre_directory.uri:
            self.backend.api.get_genre_stations(force_refresh=True)
        else:
            pandora_uri = PandoraUri.factory(uri)
            if isinstance(pandora_uri, StationUri):
                try:
                    self.pandora_station_cache.pop(pandora_uri.station_id)
                except KeyError:
                    # Item not in cache, ignore
                    pass
            else:
                raise ValueError('Unexpected URI type to perform refresh of Pandora directory: {}.'
                                 .format(pandora_uri.uri_type))

    def search(self, query=None, uris=None, exact=False, **kwargs):
        search_text = self._formatted_search_query(query)

        if not search_text:
            # No value provided for search query, abort.
            logger.info('Unsupported Pandora search query: {}'.format(query))
            return []

        search_result = self.backend.api.search(search_text, include_near_matches=False, include_genre_stations=True)

        tracks = []
        for genre in search_result.genre_stations:
            tracks.append(models.Track(uri=SearchUri(genre.token).uri,
                                       name='{} (Pandora genre)'.format(genre.station_name),
                                       artists=[models.Artist(name=genre.station_name)]))

        for song in search_result.songs:
            tracks.append(models.Track(uri=SearchUri(song.token).uri,
                                       name='{} (Pandora station)'.format(song.song_name),
                                       artists=[models.Artist(name=song.artist)]))

        artists = []
        for artist in search_result.artists:
            search_uri = SearchUri(artist.token)
            if search_uri.is_artist_search:
                station_name = '{} (Pandora artist)'.format(artist.artist)
            else:
                station_name = '{} (Pandora composer)'.format(artist.artist)
            artists.append(models.Artist(uri=search_uri.uri,
                                         name=station_name))

        return models.SearchResult(uri='pandora:search:{}'.format(search_text), tracks=tracks, artists=artists)

    def _formatted_search_query(self, query):
        search_text = []
        for (field, values) in iter(query.items()):
            if not hasattr(values, '__iter__'):
                values = [values]
            for value in values:
                if field == 'any' or field == 'artist' or field == 'track_name':
                    search_text.append(value)
        search_text = ' '.join(search_text)
        return search_text
