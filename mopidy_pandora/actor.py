from __future__ import unicode_literals

import logging
import urllib
import pykka
from mopidy import backend, models
import pandora

logger = logging.getLogger(__name__)


class PandoraBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ['pandora']

    def __init__(self, config, audio):
        super(PandoraBackend, self).__init__()
        config = config['pandora']
        settings = {
            "DECRYPTION_KEY": config["partner_decryption_key"],
            "ENCRYPTION_KEY": config["partner_encryption_key"],
            "USERNAME": config["partner_username"],
            "PASSWORD": config["partner_password"],
            "DEVICE": config["partner_device"],
        }
        self.api = pandora.APIClient.from_settings_dict(settings)
        self.api.login(username=config["username"], password=config["password"])

        self.library = PandoraLibraryProvider(backend=self)
        self.playback = PandoraPlaybackProvider(audio=audio, backend=self)


class PandoraPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self.station_token = None

    def _next_track(self, station_token):
        if self.station_token != station_token:
            self.station_token = station_token
            self.tracks = iter(())

        while True:
            try:
                return next(self.tracks)
            except StopIteration:
                self.tracks = (pandora.models.pandora.PlaylistItem.from_json(self.backend.api, station)
                               for station in self.backend.api.get_playlist(self.station_token)['items'])

    def change_track(self, track):
        track_uri = PandoraUri.parse(track.uri)
        pandora_track = self._next_track(track_uri.station_token)
        if not pandora_track:
            return False
        mopidy_track = models.Track(uri=pandora_track.audio_url)
        return super(PandoraPlaybackProvider, self).change_track(mopidy_track)


class _PandoraUriMeta(type):
    def __init__(cls, name, bases, clsdict):
        super(_PandoraUriMeta, cls).__init__(name, bases, clsdict)
        if hasattr(cls, 'scheme'):
            cls.SCHEMES[cls.scheme] = cls


class PandoraUri(object):
    __metaclass__ = _PandoraUriMeta
    SCHEMES = {}

    def __init__(self, scheme=None):
        if scheme is not None:
            self.scheme = scheme

    @property
    def uri(self):
        return "pandora:{}".format(self.scheme)

    @classmethod
    def parse(cls, uri):
        parts = [urllib.unquote(p) for p in uri.split(':')]
        uri_cls = cls.SCHEMES.get(parts[1])
        if uri_cls:
            return uri_cls(*parts[2:])
        else:
            return cls(*parts[1:])


class StationUri(PandoraUri):
    scheme = 'station'

    def __init__(self, station_token):
        super(StationUri, self).__init__()
        self.station_token = station_token

    @property
    def uri(self):
        return "{}:{}".format(super(StationUri, self).uri, self.station_token)


class TrackUri(PandoraUri):
    scheme = 'track'

    def __init__(self, station_token, track_num):
        super(TrackUri, self).__init__()
        self.station_token = station_token
        self.track_num = int(track_num)

    @property
    def uri(self):
        return "{}:{}:{}".format(super(TrackUri, self).uri, self.station_token, self.track_num)


class PandoraLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(name='Pandora', uri=PandoraUri('directory').uri)

    def __init__(self, backend):
        super(PandoraLibraryProvider, self).__init__(backend)
        self.stations = {}

    def browse(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == 'stations':
            def cache_station(station):
                station_uri = StationUri(station.token).uri
                self.stations[station_uri] = station
                return models.Ref.track(name=station.name, uri=station_uri)
            self.stations.clear()
            stations = self.backend.api.get_station_list()
            return [cache_station(station) for station in stations]

        # Root directory
        return [
            models.Ref.directory(name='Stations', uri=PandoraUri('stations').uri),
        ]

    def lookup(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == StationUri.scheme:
            station = self.stations[pandora_uri.uri]
            return [models.Track(
                name=station.name, uri=uri,
                album=models.Album(name=station.name, uri=station.detail_url, images=[station.art_url]),
            )]
