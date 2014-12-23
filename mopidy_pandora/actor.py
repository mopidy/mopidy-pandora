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

        self.library = PandoraLibraryProvider(backend=self, max_tracks=int(config['max_tracks']))
        self.playback = PandoraPlaybackProvider(audio=audio, backend=self)


class PandoraPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self.station_token = None
        self.track_num = 0

    def _next_track(self, station_token, track_num):
        #XXX what if user browses out of station and then back? that should work
        if station_token <= self.station_token:
            # Can't play a previously seen track in this station
            if track_num < self.track_num:
                return None
        else:
            self.station_token = station_token
            self.tracks = iter(())
            self.track_num = 0

        while True:
            try:
                return next(self.tracks)
            except StopIteration:
                self.tracks = iter(self.backend.api.get_playlist(station_token))

    def change_track(self, track):
        track_uri = PandoraUri.parse(track.uri)
        if track_uri.scheme != TrackUri.scheme:
            return False
        pandora_track = self._next_track(track_uri.station_token, track_uri.track_num)
        if not pandora_track:
            return False
        mopidy_track = models.Track(
            uri=pandora_track.stream_url,
            name=pandora_track.song_name,
            artist=models.Artist(name=pandora_track.artist_name, uri=pandora_track.artist_detail_url),
            album=models.Album(name=pandora_track.album_name, uri=pandora_track.album_detail_url, images=[pandora_track.album_art_url]),
        )
        return super(PandoraPlaybackProvider, self).change_track(mopidy_track)


def new_directory(name, uri):
    return models.Ref.directory(
        uri=uri.uri,
        name=name,
    )


def new_track(name, uri):
    return models.Ref.track(
        uri=uri.uri,
        name=name,
    )


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
    root_directory = new_directory('Pandora', PandoraUri('directory'))

    def __init__(self, backend, max_tracks):
        super(PandoraLibraryProvider, self).__init__(backend)
        self.max_tracks = max_tracks

    def browse(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == 'stations':
            stations = self.backend.api.get_station_list()
            return [new_directory(station.name, StationUri(station.token))
                    for station in stations]
        elif pandora_uri.scheme == StationUri.scheme:
            # Return a list of placeholder tracks.
            # We need mopidy support for dynamic playlists
            # https://github.com/mopidy/mopidy/issues/620
            return [new_track('Pandora Track #{}'.format(i),
                              TrackUri(pandora_uri.station_token, i))
                    for i in range(self.max_tracks)]

        # Root directory
        return [
            new_directory('Stations', PandoraUri('stations')),
        ]

    def lookup(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == StationUri.scheme:
            # Return a list of placeholder tracks.
            # We need mopidy support for dynamic playlists
            # https://github.com/mopidy/mopidy/issues/620
            return [models.Track(name='Pandora Track #{}'.format(i),
                                 pandora_uri=TrackUri(pandora_uri.station_token, i))
                    for i in range(self.max_tracks)]
        elif pandora_uri.scheme == TrackUri.scheme:
            return [models.Track(name='Pandora Track #{}'.format(pandora_uri.track_num), uri=uri)]
