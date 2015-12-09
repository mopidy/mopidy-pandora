from __future__ import absolute_import, unicode_literals

from mopidy import listener


class PandoraListener(listener.Listener):

    @staticmethod
    def send(event, **kwargs):
        listener.send_async(PandoraListener, event, **kwargs)

    def prepare_next_track(self, auto_play):
        pass

    def expand_tracklist(self, track, auto_play):
        pass

    def doubleclicked(self):
        pass

    def call_event(self, track_uri, pandora_event):
        pass

    def event_processed(self, track_uri):
        pass
