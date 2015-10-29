import logging
import urllib

from pandora.models.pandora import AdItem, PlaylistItem

logger = logging.getLogger(__name__)


class _PandoraUriMeta(type):
    def __init__(cls, name, bases, clsdict):  # noqa N805
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
    ADVERTISEMENT_TOKEN = "advertisement-none"

    def __init__(self, station_id, track_token, name, detail_url, art_url, audio_url='none_generated', index=0):
        super(TrackUri, self).__init__(station_id, track_token, name, detail_url, art_url)
        self.audio_url = audio_url
        self.index = index

    @classmethod
    def from_track(cls, track, index=0):

        if isinstance(track, PlaylistItem):
            return TrackUri(track.station_id, track.track_token, track.song_name, track.song_detail_url,
                            track.album_art_url, track.audio_url, index)
        elif isinstance(track, AdItem):
            return TrackUri(None, cls.ADVERTISEMENT_TOKEN, track.title, None, None, track.audio_url, index)
        else:
            raise NotImplementedError("Unsupported playlist item type")

    @property
    def uri(self):
        return "{}:{}:{}".format(
            super(TrackUri, self).uri,
            self.quote(self.audio_url),
            self.quote(self.index),
        )

    def is_ad(self):
        return self.token == self.ADVERTISEMENT_TOKEN
