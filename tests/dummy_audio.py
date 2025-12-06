"""A dummy audio actor for use in tests.

This class implements the audio API in the simplest way possible. It is used in
tests of the core and backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pykka
from mopidy import audio
from mopidy.types import DurationMs

if TYPE_CHECKING:
    from collections.abc import Callable

    from mopidy.audio import AudioProxy
    from mopidy.config import Config
    from mopidy.mixer import MixerProxy


def create_proxy(
    config: Config | None = None,
    mixer: MixerProxy | None = None,
) -> AudioProxy:
    return cast("AudioProxy", DummyAudio.start(config, mixer).proxy())


# TODO: reset position on track change?
class DummyAudio(pykka.ThreadingActor):
    def __init__(
        self,
        config: Config | None = None,
        mixer: MixerProxy | None = None,
    ) -> None:
        super().__init__()
        self.state = audio.PlaybackState.STOPPED
        self._volume = 0
        self._position = DurationMs(0)
        self._callback = None
        self._uri = None
        self._stream_changed = False
        self._tags = {}
        self._bad_uris = set()

    def set_uri(
        self,
        uri: str,
        live_stream: bool = False,  # noqa: FBT001
        download: bool = False,  # noqa: FBT001
    ) -> None:
        assert self._uri is None, "prepare change not called before set"
        self._tags = {}
        self._uri = uri
        self._stream_changed = True

    def set_source_setup_callback(self, callback: Callable) -> None:
        pass

    def set_about_to_finish_callback(self, callback: Callable) -> None:
        self._callback = callback

    def get_position(self) -> DurationMs:
        return self._position

    def set_position(self, position: DurationMs) -> bool:
        self._position = position
        audio.AudioListener.send("position_changed", position=position)
        return True

    def start_playback(self) -> bool:
        return self._change_state(audio.PlaybackState.PLAYING)

    def pause_playback(self) -> bool:
        return self._change_state(audio.PlaybackState.PAUSED)

    def prepare_change(self) -> bool:
        self._uri = None
        return True

    def stop_playback(self) -> bool:
        return self._change_state(audio.PlaybackState.STOPPED)

    def wait_for_state_change(self) -> None:
        pass

    def enable_sync_handler(self) -> None:
        pass

    def get_current_tags(self) -> dict[str, list[Any]]:
        return self._tags

    def _change_state(self, new_state):
        if not self._uri:
            return False

        if new_state == audio.PlaybackState.STOPPED and self._uri:
            self._stream_changed = True
            self._uri = None

        if self._uri is not None:
            audio.AudioListener.send("position_changed", position=0)

        if self._stream_changed:
            self._stream_changed = False
            audio.AudioListener.send("stream_changed", uri=self._uri)

        old_state, self.state = self.state, new_state
        audio.AudioListener.send(
            "state_changed",
            old_state=old_state,
            new_state=new_state,
            target_state=None,
        )

        if new_state == audio.PlaybackState.PLAYING:
            self._tags["audio-codec"] = ["fake info..."]
            audio.AudioListener.send("tags_changed", tags=["audio-codec"])

        return self._uri not in self._bad_uris

    def trigger_fake_playback_failure(self, uri):
        self._bad_uris.add(uri)

    def trigger_fake_tags_changed(self, tags):
        self._tags.update(tags)
        audio.AudioListener.send("tags_changed", tags=self._tags.keys())

    def get_about_to_finish_callback(self):
        # This needs to be called from outside the actor or we lock up.
        def wrapper():
            if self._callback:
                self.prepare_change()
                self._callback()

            if not self._uri or not self._callback:
                self._tags = {}
                audio.AudioListener.send("reached_end_of_stream")
            else:
                audio.AudioListener.send("position_changed", position=0)
                audio.AudioListener.send("stream_changed", uri=self._uri)

        return wrapper
