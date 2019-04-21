"""A dummy backend for use in tests.

This backend implements the backend API in the simplest way possible.  It is
used in tests of the frontends.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from mopidy import backend
from mopidy import listener
from mopidy.models import Ref, SearchResult

import pykka

from mopidy_pandora.listener import PandoraPlaybackListener


def create_proxy(cls, config=None, audio=None):
    return cls.start(config=config, audio=audio).proxy()


class DummyBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super(DummyBackend, self).__init__()

        self.library = DummyLibraryProvider(backend=self)
        if audio is None:
            self.playback = DummyPandoraPlaybackProvider(audio=audio, backend=self)
        else:
            self.playback = DummyPandoraPlaybackProviderWithAudioEvents(audio=audio, backend=self)

        self.uri_schemes = ['mock']


class DummyPandoraBackend(DummyBackend):

    def __init__(self, config, audio):
        super(DummyPandoraBackend, self).__init__(config, audio)
        self.uri_schemes = ['pandora']


class DummyLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri='mock:/', name='mock')

    def __init__(self, *args, **kwargs):
        super(DummyLibraryProvider, self).__init__(*args, **kwargs)
        self.dummy_library = []
        self.dummy_get_distinct_result = {}
        self.dummy_browse_result = {}
        self.dummy_find_exact_result = SearchResult()
        self.dummy_search_result = SearchResult()

    def browse(self, path):
        return self.dummy_browse_result.get(path, [])

    def get_distinct(self, field, query=None):
        return self.dummy_get_distinct_result.get(field, set())

    def lookup(self, uri):
        return [t for t in self.dummy_library if uri == t.uri]

    def refresh(self, uri=None):
        pass

    def search(self, query=None, uris=None, exact=False):
        if exact:  # TODO: remove uses of dummy_find_exact_result
            return self.dummy_find_exact_result
        return self.dummy_search_result


class DummyPlaybackProvider(backend.PlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(DummyPlaybackProvider, self).__init__(*args, **kwargs)
        self._uri = None
        self._time_position = 0

    def pause(self):
        return True

    def play(self):
        return self._uri and self._uri != 'mock:error'

    def change_track(self, track):
        """Pass a track with URI 'dummy:error' to force failure"""
        self._uri = track.uri
        self._time_position = 0
        return True

    def prepare_change(self):
        pass

    def resume(self):
        return True

    def seek(self, time_position):
        self._time_position = time_position
        return True

    def stop(self):
        self._uri = None
        return True

    def get_time_position(self):
        return self._time_position


class DummyPandoraPlaybackProvider(DummyPlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(DummyPandoraPlaybackProvider, self).__init__(*args, **kwargs)

    def change_track(self, track):
        listener.send(PandoraPlaybackListener, 'track_changing', track=track)
        return super(DummyPandoraPlaybackProvider, self).change_track(track)


class DummyPandoraPlaybackProviderWithAudioEvents(backend.PlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(DummyPandoraPlaybackProviderWithAudioEvents, self).__init__(*args, **kwargs)

    def change_track(self, track):
        listener.send(PandoraPlaybackListener, 'track_changing', track=track)
        return super(DummyPandoraPlaybackProviderWithAudioEvents, self).change_track(track)
