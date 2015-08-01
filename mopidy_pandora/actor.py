from __future__ import unicode_literals

import logging
import urllib
from pandora import BaseAPIClient, clientbuilder
from pydora.utils import iterate_forever
import pykka
from mopidy import backend, models
from mopidy_pandora.client import MopidyPandoraAPIClient

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
            "PARTNER_USER": config["partner_username"],
            "PARTNER_PASSWORD": config["partner_password"],
            "DEVICE": config["partner_device"],
            "AUDIO_QUALITY": config.get("preferred_audio_quality", BaseAPIClient.MED_AUDIO_QUALITY)
        }
        self.api = clientbuilder.SettingsDictBuilder(settings, client_class=MopidyPandoraAPIClient).build()
        self.api.login(config["username"], config["password"])

        self.library = PandoraLibraryProvider(backend=self, sort_order=config['sort_order'])
        self.playback = PandoraPlaybackProvider(audio=audio, backend=self)


class PandoraPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self.station = None
        self.station_iter = None
        # TODO: add callback when gapless playback is supported in Mopidy > 1.1
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_about_to_finish_callback(self.callback).get()

    def callback(self):
        self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def change_track(self, track):
        station_token = PandoraUri.parse(track.uri).station_token

        if not self.station or station_token != self.station.token:
            self.station = self.backend.api.get_station(station_token)
            self.station_iter = iterate_forever(self.station.get_playlist)

        return super(PandoraPlaybackProvider, self).change_track(self.get_next_track())

    def get_next_track(self):
        consecutive_track_skips = 0
        for track in self.station_iter:
            if track.audio_url and track.get_is_playable():
                return models.Track(uri=TrackUri.from_track(track).uri)
            else:
                consecutive_track_skips += 1
                logger.warning('Track is not playable: %s', TrackUri.from_track(track).uri)
                if consecutive_track_skips > 5:
                    self.station = None
                    raise Exception('Unplayable track limit exceeded')

    def translate_uri(self, uri):
        return PandoraUri.parse(uri).audio_url


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

    def __init__(self, station_token, name, detail_url, art_url, audio_url='none_generated'):
        super(TrackUri, self).__init__(station_token, name, detail_url, art_url)
        self.audio_url = audio_url

    @classmethod
    def from_track(cls, track):
        return TrackUri(track.station_id, track.song_name, track.album_detail_url, track.album_art_url, track.audio_url)

    @property
    def uri(self):
        return "{}:{}".format(
            super(TrackUri, self).uri,
            self.quote(self.audio_url),
        )


class PandoraLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(name='Pandora', uri=PandoraUri('directory').uri)

    def __init__(self, backend, sort_order):
        self.sort_order = sort_order.upper()
        super(PandoraLibraryProvider, self).__init__(backend)

    def browse(self, uri):

        pandora_uri = PandoraUri.parse(uri)

        if pandora_uri.scheme != StationUri.scheme:
            stations = self.backend.api.get_station_list()
            if self.sort_order == "A-Z":
                stations.sort(key=lambda x: x.name, reverse=False)
            return [models.Ref.directory(name=station.name, uri=StationUri.from_station(station).uri)
                    for station in stations]
        else:
            return [models.Ref.track(name="{} (Repeat Track)".format(pandora_uri.name),
                                     uri=TrackUri(pandora_uri.station_token, pandora_uri.name, pandora_uri.detail_url,
                                                  pandora_uri.art_url).uri)]

    def lookup(self, uri):
        pandora_uri = PandoraUri.parse(uri)
        if pandora_uri.scheme == TrackUri.scheme:
            return [models.Track(name="{} (Repeat Track)".format(pandora_uri.name), uri=uri,
                                 artists=[models.Artist(name="Pandora")],
                                 album=models.Album(name=pandora_uri.name, uri=pandora_uri.detail_url,
                                                    images=[pandora_uri.art_url]))]
