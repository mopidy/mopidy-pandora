import logging

import urllib

from mopidy import backend, models
from mopidy.internal import encoding

from pandora import BaseAPIClient, clientbuilder

from pydora.utils import iterate_forever

import pykka

import requests

from mopidy_pandora.client import MopidyPandoraAPIClient


logger = logging.getLogger(__name__)


class PandoraBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super(PandoraBackend, self).__init__()
        self._config = config['pandora']
        settings = {
            "API_HOST": self._config.get("api_host", 'tuner.pandora.com/services/json/'),
            "DECRYPTION_KEY": self._config["partner_decryption_key"],
            "ENCRYPTION_KEY": self._config["partner_encryption_key"],
            "PARTNER_USER": self._config["partner_username"],
            "PARTNER_PASSWORD": self._config["partner_password"],
            "DEVICE": self._config["partner_device"],
            "AUDIO_QUALITY": self._config.get("preferred_audio_quality", BaseAPIClient.HIGH_AUDIO_QUALITY)
        }
        self.api = clientbuilder.SettingsDictBuilder(settings, client_class=MopidyPandoraAPIClient).build()

        self.library = PandoraLibraryProvider(backend=self, sort_order=self._config['sort_order'])
        self.playback = PandoraPlaybackProvider(audio=audio, backend=self)

        self.uri_schemes = ['pandora']

    def on_start(self):
        try:
            self.api.login(self._config["username"], self._config["password"])
        except requests.exceptions.RequestException as e:
            logger.error('Error logging in to Pandora: %s', encoding.locale_decode(e))


class PandoraPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super(PandoraPlaybackProvider, self).__init__(audio, backend)
        self._station = None
        self._station_iter = None
        # TODO: add callback when gapless playback is supported in Mopidy > 1.1
        # See: https://discuss.mopidy.com/t/has-the-gapless-playback-implementation-been-completed-yet/784/2
        # self.audio.set_about_to_finish_callback(self.callback).get()

    def callback(self):
        self.audio.set_uri(self.translate_uri(self.get_next_track())).get()

    def change_track(self, track):

        if track.uri is None:
            return False

        station_id = PandoraUri.parse(track.uri).station_id

        if not self._station or station_id != self._station.id:
            self._station = self.backend.api.get_station(station_id)
            self._station_iter = iterate_forever(self._station.get_playlist)

        try:
            next_track = self.get_next_track()
            if next_track:
                return super(PandoraPlaybackProvider, self).change_track(next_track)
        except requests.exceptions.RequestException as e:
            logger.error('Error changing track: %s', encoding.locale_decode(e))

        return False

    def get_next_track(self):
        consecutive_track_skips = 0

        for track in self._station_iter:
            try:
                is_playable = track.audio_url and track.get_is_playable()
            except requests.exceptions.RequestException as e:
                is_playable = False
                logger.error('Error checking if track is playable: %s', encoding.locale_decode(e))

            if is_playable:
                return models.Track(uri=TrackUri.from_track(track).uri)
            else:
                consecutive_track_skips += 1
                logger.warning('Track with uri ''%s'' is not playable.', TrackUri.from_track(track).uri)
                if consecutive_track_skips >= 4:
                    logger.error('Unplayable track skip limit exceeded!')
                    return None

        return None

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

        if value is None:
            value = ''

        if not isinstance(value, basestring):
            value = str(value)
        return urllib.quote(value.encode('utf8'))

    @property
    def uri(self):
        return "pandora:{}".format(self.quote(self.scheme))

    @classmethod
    def parse(cls, uri):
        parts = [urllib.unquote(p).decode('utf8') for p in uri.split(':')]
        uri_cls = cls.SCHEMES.get(parts[1])
        if uri_cls:
            return uri_cls(*parts[2:])
        else:
            return cls(*parts[1:])


class StationUri(PandoraUri):
    scheme = 'station'

    def __init__(self, station_id, station_token, name, detail_url, art_url):
        super(StationUri, self).__init__()
        self.station_id = station_id
        self.token = station_token
        self.name = name
        self.detail_url = detail_url
        self.art_url = art_url

    @classmethod
    def from_station(cls, station):
        return StationUri(station.id, station.token, station.name, station.detail_url, station.art_url)

    @property
    def uri(self):
        return "{}:{}:{}:{}:{}:{}".format(
            super(StationUri, self).uri,
            self.quote(self.station_id),
            self.quote(self.token),
            self.quote(self.name),
            self.quote(self.detail_url),
            self.quote(self.art_url),
        )


class TrackUri(StationUri):
    scheme = 'track'

    def __init__(self, station_id, track_token, name, detail_url, art_url, audio_url='none_generated'):
        super(TrackUri, self).__init__(station_id, track_token, name, detail_url, art_url)
        self.audio_url = audio_url

    @classmethod
    def from_track(cls, track):
        return TrackUri(track.station_id, track.track_token, track.song_name, track.song_detail_url,
                        track.album_art_url, track.audio_url)

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
