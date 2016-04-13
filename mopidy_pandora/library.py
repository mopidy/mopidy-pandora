from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from collections import namedtuple

from cachetools import LRUCache

from mopidy import backend, models

from pandora.models.pandora import Station

from pydora.utils import iterate_forever

from mopidy_pandora.uri import AdItemUri, GenreStationUri, GenreUri, PandoraUri, StationUri, TrackUri  # noqa I101

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

        if type(pandora_uri) is GenreUri:
            return self._browse_genre_stations(uri)

        if type(pandora_uri) is StationUri or type(pandora_uri) is GenreStationUri:
            return self._browse_tracks(uri)

    def lookup(self, uri):
        pandora_uri = PandoraUri.factory(uri)
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

                if type(pandora_uri) is AdItemUri:
                    track_kwargs['name'] = 'Advertisement'

                    if not track.title:
                        track.title = '(Title not specified)'
                    artist_kwargs['name'] = track.title

                    if not track.company_name:
                        track.company_name = '(Company name not specified)'
                    album_kwargs['name'] = track.company_name

                    album_kwargs['uri'] = track.click_through_url
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
                    album_kwargs['uri'] = track.album_detail_url
        else:
            raise ValueError('Unexpected type to perform Pandora track lookup: {}.'.format(pandora_uri.uri_type))

        track_kwargs['artists'] = [models.Artist(**artist_kwargs)]
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
                logger.exception("Failed to lookup image for Pandora URI '{}'.".format(uri))
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

    def _create_station_for_genre(self, genre_token):
        json_result = self.backend.api.create_station(search_token=genre_token)
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
        if GenreStationUri.pattern.match(station_id):
            pandora_uri = self._create_station_for_genre(station_id)
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
        if type(track_uri) is AdItemUri:
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
            if type(pandora_uri) is StationUri:
                try:
                    self.pandora_station_cache.pop(pandora_uri.station_id)
                except KeyError:
                    # Item not in cache, ignore
                    pass
            else:
                raise ValueError('Unexpected URI type to perform refresh of Pandora directory: {}.'
                                 .format(pandora_uri.uri_type))
