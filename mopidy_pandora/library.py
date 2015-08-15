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

            return [models.Ref.track(name="{} (Repeat Track)".format(pandora_uri.name),
                                     uri=TrackUri(pandora_uri.station_id, pandora_uri.token, pandora_uri.name,
                                                  pandora_uri.detail_url, pandora_uri.art_url).uri)]

    def lookup(self, uri):

        pandora_uri = PandoraUri.parse(uri)

        if pandora_uri.scheme == TrackUri.scheme:

            return [models.Track(name="{} (Repeat Track)".format(pandora_uri.name), uri=uri,
                                 artists=[models.Artist(name="Pandora")],
                                 album=models.Album(name=pandora_uri.name, uri=pandora_uri.detail_url,
                                                    images=[pandora_uri.art_url]))]

        logger.error("Failed to lookup '%s'", uri)
        return []
