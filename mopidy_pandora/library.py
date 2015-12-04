from mopidy import backend, models

from pandora.models.pandora import Station

from pydora.utils import iterate_forever

from mopidy_pandora import rpc

from mopidy_pandora.uri import GenreUri, logger, PandoraUri, StationUri, TrackUri  # noqa I101


class PandoraLibraryProvider(backend.LibraryProvider):
    ROOT_DIR_NAME = 'Pandora'
    GENRE_DIR_NAME = 'Browse Genres'
    SHUFFLE_STATION_NAME = 'QuickMix'

    root_directory = models.Ref.directory(name=ROOT_DIR_NAME, uri=PandoraUri('directory').uri)
    genre_directory = models.Ref.directory(name=GENRE_DIR_NAME, uri=PandoraUri('genres').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.upper()
        self._station = None
        self._station_iter = None
        self._uri_translation_map = {}
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):
        if uri == self.root_directory.uri:
            # Prefetch genre category list
            rpc.run_async(self.backend.api.get_genre_stations)
            return self._browse_stations()

        if uri == self.genre_directory.uri:
            return self._browse_genre_categories()

        pandora_uri = PandoraUri.parse(uri)

        if pandora_uri.scheme == GenreUri.scheme:
            return self._browse_genre_stations(uri)

        if pandora_uri.scheme == StationUri.scheme:
            return self._browse_tracks(uri)

        raise Exception("Unknown or unsupported URI type '%s'", uri)

    def lookup(self, uri):

        if PandoraUri.parse(uri).scheme == TrackUri.scheme:
            pandora_track = self.lookup_pandora_track(uri)

            if pandora_track:
                track = models.Track(name=pandora_track.song_name, uri=uri, length=pandora_track.track_length * 1000,
                                     bitrate=int(pandora_track.bitrate),
                                     artists=[models.Artist(name=pandora_track.artist_name)],
                                     album=models.Album(name=pandora_track.album_name,
                                                        uri=pandora_track.album_detail_url,
                                                        images=[pandora_track.album_art_url]))
                return [track]

        logger.error("Failed to lookup '%s'", uri)
        return []

    def _move_shuffle_to_top(self, list):

        for station in list:
            if station.name == PandoraLibraryProvider.SHUFFLE_STATION_NAME:
                # Align with 'QuickMix' being renamed to 'Shuffle' in most other Pandora front-ends.
                station.name = 'Shuffle'
                return list.insert(0, list.pop(list.index(station)))

    def _browse_stations(self):
        stations = self.backend.api.get_station_list()

        if any(stations):
            if self.sort_order == "A-Z":
                stations.sort(key=lambda x: x.name, reverse=False)

            self._move_shuffle_to_top(stations)

        station_directories = []
        for station in stations:
            station_directories.append(
                models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri))

        station_directories.insert(0, self.genre_directory)
        return station_directories

    def _browse_tracks(self, uri):
        pandora_uri = PandoraUri.parse(uri)

        # TODO: should be able to perform check on is_ad() once dynamic tracklist support is available
        # if not self._station or (not track.is_ad() and station_id != self._station.id):
        if self._station is None or (pandora_uri.station_id != '' and pandora_uri.station_id != self._station.id):

            if pandora_uri.is_genre_station_uri():
                pandora_uri = self._create_station_for_genre(pandora_uri.token)

            self._station = self.backend.api.get_station(pandora_uri.station_id)
            self._station_iter = iterate_forever(self._station.get_playlist)

        return [self.next_track()]

    def _create_station_for_genre(self, genre_token):
        json_result = self.backend.api.create_station(search_token=genre_token)
        new_station = Station.from_json(self.backend.api, json_result)

        return StationUri.from_station(new_station)

    def _browse_genre_categories(self):
        return [models.Ref.directory(name=category, uri=GenreUri(category).uri)
                for category in sorted(self.backend.api.get_genre_stations().keys())]

    def _browse_genre_stations(self, uri):
        return [models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri)
                for station in self.backend.api.get_genre_stations(refresh_cache=False)
                [GenreUri.parse(uri).category_name]]

    def lookup_pandora_track(self, uri):
        try:
            return self._uri_translation_map[uri]
        except KeyError:
            logger.error("Failed to lookup '%s' in uri translation map.", uri)
            return None

    def next_track(self):
        pandora_track = self._station_iter.next()

        if pandora_track.track_token is None:
            # TODO process add tokens properly when pydora 1.6 is available
            return self.next_track()

        track_uri = TrackUri.from_track(pandora_track)
        track = models.Ref.track(name=pandora_track.song_name, uri=track_uri.uri)

        if any(self._uri_translation_map) and track_uri.station_id != \
                TrackUri.parse(self._uri_translation_map.keys()[0]).station_id:

            # We've switched stations, clear the translation map.
            self._uri_translation_map.clear()

        self._uri_translation_map[track.uri] = pandora_track

        return track
