from __future__ import absolute_import, unicode_literals

from mopidy import backend, listener


class PandoraFrontendListener(listener.Listener):
    @staticmethod
    def send(event, **kwargs):
        listener.send_async(PandoraFrontendListener, event, **kwargs)

    def more_tracks_needed(self, auto_play):
        pass

    def process_event(self, track_uri, pandora_event):
        pass


class PandoraBackendListener(backend.BackendListener):
    @staticmethod
    def send(event, **kwargs):
        listener.send_async(PandoraBackendListener, event, **kwargs)

    def next_track_prepared(self, track, auto_play):
        pass

    def event_processed(self, track_uri):
        pass


class PandoraPlaybackListener(listener.Listener):
    @staticmethod
    def send(event, **kwargs):
        listener.send_async(PandoraPlaybackListener, event, **kwargs)

    def doubleclicked(self):
        pass

    def track_changed(self, track):
        pass
