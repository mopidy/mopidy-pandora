import logging
import re
from collections import namedtuple

from cachetools import LRUCache
from pydora.utils import iterate_forever

from mopidy import backend, models
from mopidy_pandora.uri import (  # noqa I101
    AdItemUri,
    GenreStationUri,
    GenreUri,
    GenresUri,
    PandoraUri,
    SearchUri,
    StationUri,
    TrackUri,
)

logger = logging.getLogger(__name__)

StationCacheItem = namedtuple("StationCacheItem", "station, iter")
TrackCacheItem = namedtuple("TrackCacheItem", "ref, track")


class PandoraLibraryProvider(backend.LibraryProvider):
    ROOT_DIR_NAME = "Pandora"
    GENRE_DIR_NAME = "Browse Genres"

    root_directory = models.Ref.directory(
        name=ROOT_DIR_NAME, uri=PandoraUri("directory").uri
    )
    genre_directory = models.Ref.directory(
        name=GENRE_DIR_NAME, uri=PandoraUri("genres").uri
    )

    def __init__(self, backend, sort_order):
        super().__init__(backend)
        self.sort_order = sort_order.lower()

        self.pandora_station_cache = StationCache(self, maxsize=5)
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
        logger.info(
            "Looking up Pandora {} {}...".format(
                pandora_uri.uri_type, pandora_uri.uri
            )
        )
        if isinstance(pandora_uri, SearchUri):
            # Create the station first so that it can be browsed.
            station_uri = self._create_station_for_token(pandora_uri.token)
            track = self._browse_tracks(station_uri.uri)[0]

            # Recursive call to look up first track in station that was searched for.
            return self.lookup(track.uri)

        track_kwargs = {"uri": uri}
        (album_kwargs, artist_kwargs) = {}, {}

        if isinstance(pandora_uri, TrackUri):
            try:
                track = self.lookup_pandora_track(uri)
            except KeyError:
                logger.exception(f"Failed to lookup Pandora URI '{uri}'.")
                return []
            else:
                if isinstance(pandora_uri, AdItemUri):
                    track_kwargs["name"] = "Advertisement"

                    if not track.title:
                        track.title = "(Title not specified)"
                    artist_kwargs["name"] = track.title

                    if not track.company_name:
                        track.company_name = "(Company name not specified)"
                    album_kwargs["name"] = track.company_name
                else:
                    track_kwargs["name"] = track.song_name
                    track_kwargs["length"] = track.track_length * 1000
                    try:
                        track_kwargs["bitrate"] = int(track.bitrate)
                    except TypeError:
                        # Bitrate not specified for this stream, ignore.
                        pass
                    artist_kwargs["name"] = track.artist_name
                    album_kwargs["name"] = track.album_name
        elif isinstance(pandora_uri, StationUri):
            station = self.backend.api.get_station(pandora_uri.station_id)
            track_kwargs["name"] = station.name
            artist_kwargs["name"] = "Pandora Station"
            album_kwargs["name"] = ", ".join(station.genre)
        else:
            raise ValueError(
                "Unexpected type to perform Pandora track lookup: {}.".format(
                    pandora_uri.uri_type
                )
            )

        artist_kwargs[
            "uri"
        ] = uri  # Artist lookups should just point back to the track itself.
        track_kwargs["artists"] = [models.Artist(**artist_kwargs)]
        album_kwargs[
            "uri"
        ] = uri  # Album lookups should just point back to the track itself.
        track_kwargs["album"] = models.Album(**album_kwargs)
        return [models.Track(**track_kwargs)]

    def get_images(self, uris):
        result = {}
        for uri in uris:
            image_uris = set()
            try:
                image_uri = None
                pandora_uri = PandoraUri.factory(uri)

                logger.info(
                    "Retrieving images for Pandora {} {}...".format(
                        pandora_uri.uri_type, pandora_uri.uri
                    )
                )

                if isinstance(pandora_uri, AdItemUri) or isinstance(
                    pandora_uri, TrackUri
                ):
                    track = self.lookup_pandora_track(uri)
                    if track.is_ad is True:
                        image_uri = track.image_url
                    else:
                        image_uri = track.album_art_url
                elif isinstance(pandora_uri, StationUri):
                    # GenreStations don't appear to have artwork available via the
                    # json API
                    if not isinstance(pandora_uri, GenreStationUri):
                        station = self.backend.api.get_station(
                            pandora_uri.station_id
                        )
                        image_uri = station.art_url
                else:
                    # Lookup
                    logger.warning(
                        "No images available for Pandora URIs of type '{}'.".format(
                            pandora_uri.uri_type
                        )
                    )

                if image_uri:
                    image_uris.update(
                        [image_uri.replace("http://", "https://", 1)]
                    )
            except (TypeError, KeyError):
                pandora_uri = PandoraUri.factory(uri)
                if isinstance(pandora_uri, TrackUri):
                    # Could not find the track as expected - exception.
                    logger.exception(
                        "Failed to lookup image for Pandora URI '{}'.".format(
                            uri
                        )
                    )

            result[uri] = [models.Image(uri=u) for u in image_uris]
        return result

    def _formatted_station_list(self, station_list):
        # Find QuickMix stations and move QuickMix to top
        quickmix_stations = []
        for i, station in enumerate(station_list.copy()):
            if station.is_quickmix:
                quickmix_stations = station.quickmix_stations
                if not station.name.endswith(" (marked with *)"):
                    station.name += " (marked with *)"
                station_list.insert(0, station_list.pop(i))
                break

        # Mark QuickMix stations
        for station in station_list:
            if station.id in quickmix_stations:
                if not station.name.endswith("*"):
                    station.name += "*"

        return station_list

    def _browse_stations(self):
        station_directories = []

        stations = self.backend.api.get_station_list()
        if stations:
            if self.sort_order == "a-z":
                stations.sort(key=lambda x: x.name, reverse=False)

            for station in self._formatted_station_list(stations):
                # As of version 5 of the Pandora API, station IDs and tokens
                # are always equivalent. We're using this assumption as we
                # don't have the station token available for deleting the
                # station. Detect if any Pandora API changes ever breaks this
                # assumption in the future.
                assert station.token == station.id
                station_directories.append(
                    models.Ref.directory(
                        name=station.name, uri=PandoraUri.factory(station).uri
                    )
                )

        station_directories.insert(0, self.genre_directory)

        return station_directories

    def _browse_tracks(self, uri):
        pandora_uri = PandoraUri.factory(uri)
        return [self.get_next_pandora_track(pandora_uri.station_id)]

    def _create_station_for_token(self, token):
        new_station = self.backend.api.create_station(search_token=token)

        self.refresh()
        return PandoraUri.factory(new_station)

    def _browse_genre_categories(self):
        return [
            models.Ref.directory(name=category, uri=GenreUri(category).uri)
            for category in sorted(self.backend.api.get_genre_stations().keys())
        ]

    def _browse_genre_stations(self, uri):
        return [
            models.Ref.directory(
                name=station.name, uri=PandoraUri.factory(station).uri
            )
            for station in self.backend.api.get_genre_stations()[
                PandoraUri.factory(uri).category_name
            ]
        ]

    def lookup_pandora_track(self, uri):
        return self.pandora_track_cache[uri].track

    def get_next_pandora_track(self, station_id):
        try:
            station_iter = self.pandora_station_cache[station_id].iter
            track = next(station_iter)
        except Exception:
            logger.exception("Error retrieving next Pandora track.")
            return None

        track_uri = PandoraUri.factory(track)
        if isinstance(track_uri, AdItemUri):
            track_name = "Advertisement"
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
                raise ValueError(
                    "Unexpected URI type to perform refresh of "
                    f"Pandora directory: {pandora_uri.uri_type}"
                )

    def search(self, query=None, uris=None, exact=False, **kwargs):
        search_text = self._formatted_search_query(query)

        if not search_text:
            # No value provided for search query, abort.
            logger.info(f"Unsupported Pandora search query: {query}")
            return []

        search_result = self.backend.api.search(
            search_text, include_near_matches=False, include_genre_stations=True
        )

        tracks = []
        for genre in search_result.genre_stations:
            tracks.append(
                models.Track(
                    uri=SearchUri(genre.token).uri,
                    name=f"{genre.station_name} (Pandora genre)",
                    artists=[models.Artist(name=genre.station_name)],
                )
            )

        for song in search_result.songs:
            tracks.append(
                models.Track(
                    uri=SearchUri(song.token).uri,
                    name=f"{song.song_name} (Pandora station)",
                    artists=[models.Artist(name=song.artist)],
                )
            )

        artists = []
        for artist in search_result.artists:
            search_uri = SearchUri(artist.token)
            if search_uri.is_artist_search:
                station_name = f"{artist.artist} (Pandora artist)"
            else:
                station_name = f"{artist.artist} (Pandora composer)"
            artists.append(models.Artist(uri=search_uri.uri, name=station_name))

        return models.SearchResult(
            uri=f"pandora:search:{search_text}",
            tracks=tracks,
            artists=artists,
        )

    def _formatted_search_query(self, query):
        search_text = []
        for (field, values) in iter(query.items()):
            if not hasattr(values, "__iter__"):
                values = [values]
            for value in values:
                if field == "any" or field == "artist" or field == "track_name":
                    search_text.append(value)
        search_text = " ".join(search_text)
        return search_text


class StationCache(LRUCache):
    def __init__(self, library, maxsize, getsizeof=None):
        super().__init__(maxsize, getsizeof=getsizeof)
        self.library = library

    def __missing__(self, station_id):
        if re.match("^([SRCG])", station_id):
            pandora_uri = self.library._create_station_for_token(station_id)
            station_id = pandora_uri.station_id

        station = self.library.backend.api.get_station(station_id)
        station_iter = iterate_forever(station.get_playlist)

        item = StationCacheItem(station, station_iter)
        self[station_id] = item

        return item
