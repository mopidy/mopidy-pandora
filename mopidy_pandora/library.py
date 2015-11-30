from threading import Thread
from mopidy import backend, models
from pandora.models.pandora import Station
from pydora.utils import iterate_forever
from mopidy.internal import encoding

from mopidy_pandora.uri import PandoraUri, StationUri, TrackUri, logger, GenreUri


class PandoraLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(name='Pandora', uri=PandoraUri('directory').uri)
    genre_directory = models.Ref.directory(name='Browse Genres', uri=PandoraUri('genres').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.upper()
        self._station = None
        self._station_iter = None
        self._uri_translation_map = {}
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):

        if uri == self.root_directory.uri:
            return self._browse_stations()

        if uri == self.genre_directory.uri:
            return self._browse_genre_categories()

        pandora_uri = PandoraUri.parse(uri)

        if pandora_uri.scheme == GenreUri.scheme:
            return self._browse_genre_stations(uri)

        if pandora_uri.scheme == StationUri.scheme:

            # TODO: should be able to perform check on is_ad() once dynamic tracklist support is available
            # if not self._station or (not track.is_ad() and station_id != self._station.id):
            if self._station is None or (pandora_uri.station_id != '' and pandora_uri.station_id != self._station.id):
                self._station = self.backend.api.get_station(pandora_uri.station_id)
                self._station_iter = iterate_forever(self._station.get_playlist)

            self._uri_translation_map.clear()
            tracks = []
            number_of_tracks = 3

            for i in range(0, number_of_tracks):
                tracks.append(self.next_track())

            return tracks

        raise Exception("Unknown or unsupported URI type '%s'", uri)

    def lookup(self, uri):

        if PandoraUri.parse(uri).scheme == TrackUri.scheme:

            pandora_track = self.lookup_pandora_track(uri)

            if pandora_track:

                track = models.Track(name=pandora_track.song_name, uri=uri, length=pandora_track.track_length*1000,
                                     bitrate=int(pandora_track.bitrate), artists=[models.Artist(name=pandora_track.artist_name)],
                                     album=models.Album(name=pandora_track.album_name, uri=pandora_track.album_detail_url,
                                                        images=[pandora_track.album_art_url]))
                return [track]

        logger.error("Failed to lookup '%s'", uri)
        return []

    def _prep_station_list(self, list):

        index = 0
        for item in list:
            if item.name == "QuickMix":
                index = list.index(item)
                break

        list.insert(0, list.pop(index))

    def _browse_stations(self):
        stations = self.backend.api.get_station_list()

        if any(stations) and self.sort_order == "A-Z":
            stations.sort(key=lambda x: x.name, reverse=False)
            self._prep_station_list(stations)

        station_directories = []
        for station in stations:
            station_directories.append(
                models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri))

        station_directories.insert(0, self.genre_directory)

        return station_directories

    def _browse_genre_categories(self):
        return [models.Ref.directory(name=category, uri=GenreUri(category).uri)
                for category in sorted(self.backend.api.get_genre_stations().keys())]

    def _browse_genre_stations(self, uri):
        return [models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri)
                for station in self.backend.api.get_genre_stations()[GenreUri.parse(uri).category_name]]

    def lookup_pandora_track(self, uri):
        try:
            return self._uri_translation_map[uri]
        except KeyError as e:
            logger.error("Failed to lookup '%s' in uri translation map: %s", uri, encoding.locale_decode(e))
            return None

    def next_track(self):
        pandora_track = self._station_iter.next()

        if pandora_track.track_token is None:
            # TODO process add tokens properly when pydora 1.6 is available
            return self.next_track()

        track = models.Ref.track(name=pandora_track.song_name, uri=TrackUri.from_track(pandora_track).uri)
        self._uri_translation_map[track.uri] = pandora_track

        return track
