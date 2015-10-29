from mopidy import backend, models

from mopidy_pandora.uri import PandoraUri, StationUri, TrackUri, logger


class PandoraLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(name='Pandora', uri=PandoraUri('directory').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.upper()
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):

        if uri == self.root_directory.uri:
            stations = self.backend.api.get_station_list()

            if any(stations) and self.sort_order == "A-Z":
                stations.sort(key=lambda x: x.name, reverse=False)

            return [models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri)
                    for station in stations]
        else:

            pandora_uri = PandoraUri.parse(uri)

            tracks = []
            number_of_tracks = 1
            if self.backend.supports_events:
                number_of_tracks = 3
            for i in range(0, number_of_tracks):
                tracks.append(models.Ref.track(name=pandora_uri.name,
                                               uri=TrackUri(pandora_uri.station_id, pandora_uri.token, pandora_uri.name,
                                                            pandora_uri.detail_url, pandora_uri.art_url,
                                                            index=str(i)).uri))

            return tracks

    def lookup(self, uri):

        pandora_uri = PandoraUri.parse(uri)

        if pandora_uri.scheme == TrackUri.scheme:

            return [models.Track(name=pandora_uri.name, uri=uri,
                                 artists=[models.Artist(name="Pandora")],
                                 album=models.Album(name=pandora_uri.name, uri=pandora_uri.detail_url,
                                                    images=[pandora_uri.art_url]))]

        logger.error("Failed to lookup '%s'", uri)
        return []
