from __future__ import absolute_import, unicode_literals

from mopidy import listener


class PandoraListener(listener.Listener):

    @staticmethod
    def send(event, **kwargs):
        listener.send_async(PandoraListener, event, **kwargs)

    def end_of_tracklist_reached(self):
        pass

    def add_next_pandora_track(self, track):
        pass

    def prepare_change(self):
        pass

    def doubleclicked(self):
        pass

    def call_event(self, track_uri, pandora_event):
        pass

    def event_processed(self, track_uri):
        pass

    def stop(self):
        pass
