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
            "API_HOST": config.get("api_host", 'tuner.pandora.com/services/json/'),
            "DECRYPTION_KEY": config["partner_decryption_key"],
            "ENCRYPTION_KEY": config["partner_encryption_key"],
            "USERNAME": config["partner_username"],
            "PASSWORD": config["partner_password"],
            "DEVICE": config["partner_device"],
            "DEFAULT_AUDIO_QUALITY": config.get("preferred_audio_quality", 'mediumQuality'),
            "SORT_ORDER": config["sort_order"]
        }
        self.api = pandora.APIClient.from_settings_dict(settings)
        self.api.login(username=config["username"], password=config["password"])

        self.library = PandoraLibraryProvider(backend=self, sort_order=config["sort_order"])
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

    def quote(self, value):
        return urllib.quote(value) if value is not None else ''

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

    def __init__(self, station_token, name, detail_url, art_url):
        super(StationUri, self).__init__()
        self.station_token = station_token
        self.name = name
        self.detail_url = detail_url
        self.art_url = art_url

    @classmethod
    def from_station(cls, station):
        return StationUri(station.token, station.name, station.detail_url, station.art_url)

    @property
    def uri(self):
        return "{}:{}:{}:{}:{}".format(
            super(StationUri, self).uri,
            self.quote(self.station_token),
            self.quote(self.name),
            self.quote(self.detail_url),
            self.quote(self.art_url),
        )


class TrackUri(StationUri):
    scheme = 'track'


class PandoraLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(name='Pandora', uri=PandoraUri('directory').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.upper()
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == 'stations':
            stations = self.backend.api.get_station_list()
            if self.sort_order == "A-Z":
                stations.sort(key=lambda x: x.name, reverse=False)
            return [models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri)
                    for station in stations]
        elif pandora_uri.scheme == StationUri.scheme:
            name = "{} (Repeat Track)".format(pandora_uri.name)
            return [models.Ref.track(name=name, uri=TrackUri(pandora_uri.station_token, name, pandora_uri.detail_url, pandora_uri.art_url).uri)]

        # Root directory
        return [
            models.Ref.directory(name='Stations', uri=PandoraUri('stations').uri),
        ]

    def lookup(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == TrackUri.scheme:
            return [models.Track(name=pandora_uri.name, uri=uri,
                                 album=models.Album(name=pandora_uri.name, uri=pandora_uri.detail_url, images=[pandora_uri.art_url]))]
