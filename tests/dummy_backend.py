"""A dummy backend for use in tests.

This backend implements the backend API in the simplest way possible.  It is
used in tests of the frontends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

import pykka
from mopidy import backend, listener
from mopidy.models import Ref, SearchResult
from mopidy.types import DurationMs, Uri, UriScheme

from mopidy_pandora.listener import PandoraPlaybackListener

if TYPE_CHECKING:
    from mopidy.audio import AudioProxy
    from mopidy.config import Config


def create_proxy(cls, config=None, audio=None):
    return cls.start(config=config, audio=audio).proxy()


class DummyBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes: ClassVar[list[UriScheme]] = [UriScheme("mock")]

    def __init__(self, config: Config, audio: AudioProxy | None) -> None:
        super().__init__()

        self.library = DummyLibraryProvider(backend=self)

        self.playback = (
            DummyPandoraPlaybackProvider(audio=audio, backend=self)
            if audio is None
            else DummyPandoraPlaybackProviderWithAudioEvents(audio=audio, backend=self)
        )


class DummyPandoraBackend(DummyBackend):
    uri_schemes: ClassVar[list[UriScheme]] = [UriScheme("pandora")]

    def __init__(self, config: Config, audio: AudioProxy | None) -> None:
        super().__init__(config, audio)


class DummyLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri=Uri("mock:/"), name="mock")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dummy_library = []
        self.dummy_get_distinct_result = {}
        self.dummy_browse_result = {}
        self.dummy_find_exact_result = SearchResult()
        self.dummy_search_result = SearchResult()

    @override
    def browse(self, uri):
        return self.dummy_browse_result.get(uri, [])

    @override
    def get_distinct(self, field, query=None):
        return self.dummy_get_distinct_result.get(field, set())

    @override
    def lookup(self, uri):
        return [t for t in self.dummy_library if uri == t.uri]

    @override
    def refresh(self, uri=None):
        pass

    @override
    def search(self, query=None, uris=None, exact=False):
        if exact:  # TODO: remove uses of dummy_find_exact_result
            return self.dummy_find_exact_result
        return self.dummy_search_result


class DummyPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio: AudioProxy, backend: backend.Backend):
        super().__init__(audio, backend)
        self._uri = None
        self._time_position = DurationMs(0)

    @override
    def pause(self):
        return True

    @override
    def play(self):
        return self._uri is not None and self._uri != "mock:error"

    @override
    def change_track(self, track):
        """Pass a track with URI 'dummy:error' to force failure"""
        self._uri = track.uri
        self._time_position = DurationMs(0)
        return True

    @override
    def prepare_change(self):
        pass

    @override
    def resume(self):
        return True

    @override
    def seek(self, time_position):
        self._time_position = time_position
        return True

    @override
    def stop(self):
        self._uri = None
        return True

    @override
    def get_time_position(self):
        return self._time_position


class DummyPandoraPlaybackProvider(DummyPlaybackProvider):
    @override
    def change_track(self, track):
        listener.send(PandoraPlaybackListener, "track_changing", track=track)
        return super().change_track(track)


class DummyPandoraPlaybackProviderWithAudioEvents(backend.PlaybackProvider):
    @override
    def change_track(self, track):
        listener.send(PandoraPlaybackListener, "track_changing", track=track)
        return super().change_track(track)
