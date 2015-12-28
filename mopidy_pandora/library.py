import logging

from collections import OrderedDict

from mopidy import backend, models

from pandora.models.pandora import Station

from pydora.utils import iterate_forever

from mopidy_pandora import utils
from mopidy_pandora.uri import AdItemUri, GenreStationUri, GenreUri, PandoraUri, StationUri, TrackUri  # noqa I101

logger = logging.getLogger(__name__)


class PandoraLibraryProvider(backend.LibraryProvider):
    ROOT_DIR_NAME = 'Pandora'
    GENRE_DIR_NAME = 'Browse Genres'

    root_directory = models.Ref.directory(name=ROOT_DIR_NAME, uri=PandoraUri('directory').uri)
    genre_directory = models.Ref.directory(name=GENRE_DIR_NAME, uri=PandoraUri('genres').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.lower()
        self._station = None
        self._station_iter = None

        self._pandora_track_cache = OrderedDict()
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):
        if uri == self.root_directory.uri:
            return self._browse_stations()

        if uri == self.genre_directory.uri:
            return self._browse_genre_categories()

        pandora_uri = PandoraUri.factory(uri)

        if type(pandora_uri) is GenreUri:
            return self._browse_genre_stations(uri)

        if type(pandora_uri) is StationUri or type(pandora_uri) is GenreStationUri:
            return self._browse_tracks(uri)

        raise Exception("Unknown or unsupported URI type '{}'".format(uri))

    def lookup(self, uri):

        pandora_uri = PandoraUri.factory(uri)
        if isinstance(pandora_uri, TrackUri):
            try:
                pandora_track = self.lookup_pandora_track(uri)
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

                    if not pandora_track.title:
                        pandora_track.title = '(Title not specified)'
                    artist_kwargs['name'] = pandora_track.title

                    if not pandora_track.company_name:
                        pandora_track.company_name = '(Company name not specified)'
                    album_kwargs['name'] = pandora_track.company_name

                    album_kwargs['uri'] = pandora_track.click_through_url
                else:
                    track_kwargs['name'] = pandora_track.song_name
                    track_kwargs['length'] = pandora_track.track_length * 1000
                    track_kwargs['bitrate'] = int(pandora_track.bitrate)
                    artist_kwargs['name'] = pandora_track.artist_name
                    album_kwargs['name'] = pandora_track.album_name
                    album_kwargs['uri'] = pandora_track.album_detail_url
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
                pandora_track = self.lookup_pandora_track(uri)
                if pandora_track.is_ad is True:
                    image_uri = pandora_track.image_url
                else:
                    image_uri = pandora_track.album_art_url
                if image_uri:
                    image_uris.update([image_uri])
            except (TypeError, KeyError):
                logger.exception("Failed to lookup image for Pandora URI '{}'.".format(uri))
                pass
            result[uri] = [models.Image(uri=u) for u in image_uris]
        return result

    def _cache_pandora_track(self, track, pandora_track):
        self._pandora_track_cache[track.uri] = pandora_track

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
        # Prefetch genre category list
        utils.run_async(self.backend.api.get_genre_stations)()

        station_directories = []

        stations = self.backend.api.get_station_list()
        if stations:
            if self.sort_order == 'a-z':
                stations.sort(key=lambda x: x.name, reverse=False)

            for station in self._formatted_station_list(stations):
                station_directories.append(
                    models.Ref.directory(name=station.name, uri=PandoraUri.factory(station).uri))

        station_directories.insert(0, self.genre_directory)

        return station_directories

    def _browse_tracks(self, uri):
        pandora_uri = PandoraUri.factory(uri)

        if self._station is None or (pandora_uri.station_id != self._station.id):

            if type(pandora_uri) is GenreStationUri:
                # TODO: Check if station exists before creating?
                pandora_uri = self._create_station_for_genre(pandora_uri.token)

            self._station = self.backend.api.get_station(pandora_uri.station_id)
            self._station_iter = iterate_forever(self._station.get_playlist)

        return [self.get_next_pandora_track()]

    def _create_station_for_genre(self, genre_token):
        json_result = self.backend.api.create_station(search_token=genre_token)
        new_station = Station.from_json(self.backend.api, json_result)

        # Invalidate the cache so that it is refreshed on the next request
        self.backend.api._station_list_cache.popitem()

        return PandoraUri.factory(new_station)

    def _browse_genre_categories(self):
        return [models.Ref.directory(name=category, uri=GenreUri(category).uri)
                for category in sorted(self.backend.api.get_genre_stations().keys())]

    def _browse_genre_stations(self, uri):
        return [models.Ref.directory(name=station.name, uri=PandoraUri.factory(station).uri)
                for station in self.backend.api.get_genre_stations()
                [PandoraUri.factory(uri).category_name]]

    def lookup_pandora_track(self, uri):
        return self._pandora_track_cache[uri]

    def get_next_pandora_track(self):
        try:
            pandora_track = self._station_iter.next()
        # except requests.exceptions.RequestException as e:
        #     logger.error('Error retrieving next Pandora track: {}'.format(encoding.locale_decode(e)))
        #     return None
        # except StopIteration:
        #     # TODO: workaround for https://github.com/mcrute/pydora/issues/36
        #     logger.error("Failed to retrieve next track for station '{}' from Pandora server".format(
        #         self._station.name))
        #     return None
        except Exception:
            # TODO: Remove this catch-all exception once we've figured out how to deal with all of them
            logger.exception('Error retrieving next Pandora track.')
            return None

        track_uri = PandoraUri.factory(pandora_track)

        if type(track_uri) is AdItemUri:
            track_name = 'Advertisement'
        else:
            track_name = pandora_track.song_name

        track = models.Ref.track(name=track_name, uri=track_uri.uri)

        self._cache_pandora_track(track, pandora_track)
        return track
