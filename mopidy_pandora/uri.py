from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import urllib
from mopidy import compat

from pandora.models.pandora import AdItem, GenreStation, PlaylistItem, Station

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

    def __str__(self):
        return '{}:{uri_type}'.format(self.SCHEME, **self.encoded_attributes)

    @property
    def encoded_attributes(self):
        encoded_dict = {}
        for k, v in self.__dict__.items():
            encoded_dict[k] = PandoraUri.encode(v)

        return encoded_dict

    @property
    def uri(self):
        return str(self)

    @classmethod
    def encode(cls, value):
        if value is None:
            value = ''
        if isinstance(value, compat.text_type):
            value = value.encode('utf-8')
        value = urllib.quote(value)
        return value

    @classmethod
    def decode(cls, value):
        try:
            return urllib.unquote(compat.text_type(value))
        except UnicodeError:
            return urllib.unquote(bytes(value).decode('utf-8'))

    @classmethod
    def factory(cls, obj):
        if isinstance(obj, compat.text_type) or isinstance(obj, compat.string_types):
            return PandoraUri._from_uri(obj)
        elif isinstance(obj, Station) or isinstance(obj, GenreStation):
            return PandoraUri._from_station(obj)
        elif isinstance(obj, PlaylistItem) or isinstance(obj, AdItem):
            return PandoraUri._from_track(obj)
        else:
            raise NotImplementedError("Unsupported URI object type '{}'".format(obj))

    @classmethod
    def _from_uri(cls, uri):
        parts = [cls.decode(p) for p in uri.split(':')]
        if not parts or parts[0] != PandoraUri.SCHEME or len(parts) < 2:
            raise NotImplementedError('Not a Pandora URI: {}'.format(uri))
        uri_cls = cls.TYPES.get(parts[1])
        if uri_cls:
            return uri_cls(*parts[2:])
        else:
            raise NotImplementedError("Unsupported Pandora URI type '{}'".format(uri))

    @classmethod
    def _from_station(cls, station):
        if isinstance(station, Station) or isinstance(station, GenreStation):
            if station.id.startswith('G') and station.id == station.token:
                return GenreStationUri(station.id, station.token)
            return StationUri(station.id, station.token)
        else:
            raise NotImplementedError("Unsupported station item type '{}'".format(station))

    @classmethod
    def _from_track(cls, track):
        if isinstance(track, PlaylistItem):
            return PlaylistItemUri(track.station_id, track.track_token)
        elif isinstance(track, AdItem):
            return AdItemUri(track.station_id, track.ad_token)
        else:
            raise NotImplementedError("Unsupported playlist item type '{}'".format(track))


class GenreUri(PandoraUri):
    uri_type = 'genre'

    def __init__(self, category_name):
        super(GenreUri, self).__init__(self.uri_type)
        self.category_name = category_name

    def __repr__(self):
        return '{}:{category_name}'.format(
            super(GenreUri, self).__repr__(),
            **self.__dict__
        )

    def __str__(self):
        return '{}:{category_name}'.format(
            super(GenreUri, self).__str__(),
            **self.encoded_attributes
        )


class StationUri(PandoraUri):
    uri_type = 'station'

    def __init__(self, station_id, token):
        super(StationUri, self).__init__(self.uri_type)
        self.station_id = station_id
        self.token = token

    def __repr__(self):
        return '{}:{station_id}:{token}'.format(
            super(StationUri, self).__repr__(),
            **self.__dict__
        )

    def __str__(self):
        return '{}:{station_id}:{token}'.format(
            super(StationUri, self).__str__(),
            **self.encoded_attributes
        )


class GenreStationUri(StationUri):
    uri_type = 'genre_station'

    def __init__(self, station_id, token):
        # Check that this really is a Genre station as opposed to a regular station.
        # Genre station IDs and tokens always start with 'G'.
        assert station_id.startswith('G')
        assert token.startswith('G')
        super(GenreStationUri, self).__init__(station_id, token)


class TrackUri(PandoraUri):
    uri_type = 'track'


class PlaylistItemUri(TrackUri):

    def __init__(self, station_id, token):
        super(PlaylistItemUri, self).__init__(self.uri_type)
        self.station_id = station_id
        self.token = token

    def __repr__(self):
        return '{}:{station_id}:{token}'.format(
            super(PlaylistItemUri, self).__repr__(),
            **self.__dict__
        )

    def __str__(self):
        return '{}:{station_id}:{token}'.format(
            super(PlaylistItemUri, self).__str__(),
            **self.encoded_attributes
        )


class AdItemUri(TrackUri):
    uri_type = 'ad'

    def __init__(self, station_id, ad_token):
        super(AdItemUri, self).__init__(self.uri_type)
        self.station_id = station_id
        self.ad_token = ad_token

    def __repr__(self):
        return '{}:{station_id}:{ad_token}'.format(
            super(AdItemUri, self).__repr__(),
            **self.__dict__
        )

    def __str__(self):
        return '{}:{station_id}:{ad_token}'.format(
            super(AdItemUri, self).__str__(),
            **self.encoded_attributes
        )
