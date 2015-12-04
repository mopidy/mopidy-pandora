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


class GenreUri(PandoraUri):
    scheme = 'genre'

    def __init__(self, category_name):
        super(GenreUri, self).__init__()
        self.category_name = category_name

    @property
    def uri(self):
        return "{}:{}".format(
            super(GenreUri, self).uri,
            self.quote(self.category_name),
        )


class StationUri(PandoraUri):
    scheme = 'station'

    def __init__(self, station_id, token):
        super(StationUri, self).__init__()
        self.station_id = station_id
        self.token = token

    @property
    def is_genre_station_uri(self):
        return self.station_id.startswith('G') and self.station_id == self.token

    @classmethod
    def from_station(cls, station):
        return StationUri(station.id, station.token)

    @property
    def uri(self):
        return "{}:{}:{}".format(
            super(StationUri, self).uri,
            self.quote(self.station_id),
            self.quote(self.token),
        )


class TrackUri(StationUri):
    scheme = 'track'
    ADVERTISEMENT_TOKEN = "advertisement"

    def __init__(self, station_id, token):
        super(TrackUri, self).__init__(station_id, token)

    @classmethod
    def from_track(cls, track):
        if isinstance(track, PlaylistItem):
            return TrackUri(track.station_id, track.track_token)
        elif isinstance(track, AdItem):
            return TrackUri(track.station_id, cls.ADVERTISEMENT_TOKEN)
        else:
            raise NotImplementedError("Unsupported playlist item type")

    @property
    def uri(self):
        return "{}".format(
            super(TrackUri, self).uri,
        )

    @property
    def is_ad_uri(self):
        return self.token == self.ADVERTISEMENT_TOKEN
