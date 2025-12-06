import queue
from typing import ClassVar
from unittest import mock

import pykka
from mopidy import core, models
from mopidy.types import DurationMs, Uri

from tests import dummy_audio, dummy_backend
from tests.dummy_audio import DummyAudio
from tests.dummy_backend import DummyBackend, DummyPandoraBackend


class DummyMopidyInstance:
    tracks: ClassVar[list[models.Track]] = [
        models.Track(  # Regular track
            uri=Uri("pandora:track:id_mock:token_mock1"),
            length=DurationMs(40000),
        ),
        models.Track(  # Regular track
            uri=Uri("pandora:track:id_mock:token_mock2"),
            length=DurationMs(40000),
        ),
        models.Track(  # Advertisement
            uri=Uri("pandora:ad:id_mock:token_mock3"),
            length=DurationMs(40000),
        ),
        models.Track(  # Not a pandora track
            uri=Uri("mock:track:id_mock:token_mock4"),
            length=DurationMs(40000),
        ),
        models.Track(  # Different station
            uri=Uri("pandora:track:id_mock_other:token_mock5"),
            length=DurationMs(40000),
        ),
        models.Track(  # No duration
            uri=Uri("pandora:track:id_mock:token_mock6"),
            length=None,
        ),
    ]

    uris: ClassVar[list[Uri]] = [
        Uri("pandora:track:id_mock:token_mock1"),
        Uri("pandora:track:id_mock:token_mock2"),
        Uri("pandora:ad:id_mock:token_mock3"),
        Uri("mock:track:id_mock:token_mock4"),
        Uri("pandora:track:id_mock_other:token_mock5"),
        Uri("pandora:track:id_mock:token_mock6"),
    ]

    def __init__(self) -> None:
        config = {"core": {"max_tracklist_length": 10000}}

        self.audio = dummy_audio.create_proxy(DummyAudio)
        self.backend = dummy_backend.create_proxy(DummyPandoraBackend, audio=self.audio)
        self.non_pandora_backend = dummy_backend.create_proxy(
            DummyBackend, audio=self.audio
        )

        self.core = core.Core.start(
            config,
            audio=self.audio,
            backends=[self.backend, self.non_pandora_backend],
        ).proxy()

        def lookup(uris):
            result = {uri: [] for uri in uris}
            for track in self.tracks:
                if track.uri in result:
                    result[track.uri].append(track)
            return result

        self.core.library.lookup = lookup
        self.tl_tracks = self.core.tracklist.add(uris=self.uris).get()

        self.events = queue.Queue()

        def send(cls, event, **kwargs):
            self.events.put((cls, event, kwargs))

        self.patcher = mock.patch("mopidy.listener.send")
        self.send_mock = self.patcher.start()
        self.send_mock.side_effect = send

        self.actor_register = [self.backend, self.core, self.audio]

    def replay_events(self, until=None):
        while True:
            try:
                e = self.events.get(timeout=0.1)
                cls, event, kwargs = e
                if event == until:
                    break
                for actor in self.actor_register:
                    if isinstance(actor, pykka.ActorProxy):
                        if isinstance(actor._actor, cls):
                            actor.on_event(event, **kwargs).get()
                    elif isinstance(actor, cls):
                        actor.on_event(event, **kwargs)
            except queue.Empty:
                # All events replayed.
                break
