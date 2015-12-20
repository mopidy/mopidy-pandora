import logging
import urllib

from pandora.models.pandora import AdItem, PlaylistItem
logger = logging.getLogger(__name__)


class _PandoraUriMeta(type):
    def __init__(cls, name, bases, clsdict):  # noqa N805
        super(_PandoraUriMeta, cls).__init__(name, bases, clsdict)
        if hasattr(cls, 'uri_type'):
            cls.TYPES[cls.uri_type] = cls


class PandoraUri(object):
    __metaclass__ = _PandoraUriMeta
    TYPES = {}
    SCHEME = 'pandora'

    def __init__(self, uri_type=None):
        self.uri_type = uri_type

    def __repr__(self):
        return '{}:{uri_type}'.format(self.SCHEME, **self.__dict__)

    @property
    def encoded_attributes(self):
        encoded_dict = dict(self.__dict__)
        for k, v in encoded_dict.items():
            encoded_dict[k] = PandoraUri.encode(v)

        return encoded_dict

    @property
    def uri(self):
        return repr(self)

    @classmethod
    def encode(cls, value):
        if value is None:
            value = ''

        if not isinstance(value, basestring):
            value = str(value)
        return urllib.quote(value.encode('utf8'))

    @classmethod
    def decode(cls, value):
        return urllib.unquote(value).decode('utf8')

    @classmethod
    def parse(cls, uri):
        parts = [cls.decode(p) for p in uri.split(':')]
        uri_cls = cls.TYPES.get(parts[1])
        if uri_cls:
            return uri_cls(*parts[2:])
        else:
            return cls(*parts[1:])


class GenreUri(PandoraUri):
    uri_type = 'genre'

    def __init__(self, category_name):
        super(GenreUri, self).__init__(self.uri_type)
        self.category_name = category_name

    def __repr__(self):
        return '{}:{category_name}'.format(
            super(GenreUri, self).__repr__(),
            **self.encoded_attributes
        )

    @property
    def category_name(self):
        return PandoraUri.decode(self.category_name)

    @category_name.setter
    def category_name(self, value):
        self.category_name = PandoraUri.encode(value)


# TODO: refactor genres and ads into their own types, then check for those types
#       in the code rather than using is_* methods.
class StationUri(PandoraUri):
    uri_type = 'station'

    # TODO: remove station token if it is not used anywhere?
    def __init__(self, station_id, token):
        super(StationUri, self).__init__(self.uri_type)
        self.station_id = station_id
        self.token = token

    def __repr__(self):
        return '{}:{station_id}:{token}'.format(
            super(StationUri, self).__repr__(),
            **self.encoded_attributes
        )

    @property
    def is_genre_station_uri(self):
        return self.station_id.startswith('G') and self.station_id == self.token

    @classmethod
    def from_station(cls, station):
        return StationUri(station.id, station.token)


# TODO: switch parent to PandoraUri
class TrackUri(PandoraUri):
    uri_type = 'track'
    ADVERTISEMENT_TOKEN = 'advertisement'

    def __init__(self, station_id, token):
        super(TrackUri, self).__init__(self.uri_type)
        self.station_id = station_id
        self.token = token

    @classmethod
    def from_track(cls, track):
        if isinstance(track, PlaylistItem):
            return TrackUri(track.station_id, track.track_token)
        elif isinstance(track, AdItem):
            return TrackUri(track.station_id, cls.ADVERTISEMENT_TOKEN)
        else:
            raise NotImplementedError('Unsupported playlist item type')

    def __repr__(self):
        return '{}:{station_id}:{token}'.format(
            super(TrackUri, self).__repr__(),
            **self.encoded_attributes
        )

    @property
    def is_ad_uri(self):
        return self.token == self.ADVERTISEMENT_TOKEN
