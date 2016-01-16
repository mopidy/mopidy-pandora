from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from mopidy import core

import pykka

from mopidy_pandora import listener
from mopidy_pandora.monitor import EventMonitor
from mopidy_pandora.uri import PandoraUri

logger = logging.getLogger(__name__)


def only_execute_for_pandora_uris(func):
    """ Function decorator intended to ensure that "func" is only executed if a Pandora track
        is currently playing. Allows CoreListener events to be ignored if they are being raised
        while playing non-Pandora tracks.

    :param func: the function to be executed
    :return: the return value of the function if it was run, or 'None' otherwise.
    """
    from functools import wraps

    @wraps(func)
    def check_pandora(self, *args, **kwargs):
        """ Check if a pandora track is currently being played.

        :param args: all arguments will be passed to the target function
        :param kwargs: active_uri should contain the uri to be checked, all other kwargs
               will be passed to the target function
        :return: the return value of the function if it was run or 'None' otherwise.
        """
        try:
            PandoraUri.factory(self.core.playback.get_current_tl_track().get().track.uri)
            return func(self, *args, **kwargs)
        except (AttributeError, NotImplementedError):
            # Not playing a Pandora track. Don't do anything.
            pass

    return check_pandora


class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraBackendListener,
                      listener.PandoraPlaybackListener, listener.EventMonitorListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config['pandora']
        self.auto_setup = self.config.get('auto_setup')

        self.setup_required = True
        self.core = core

        self.event_monitor = EventMonitor(config, core)

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            if self.core.tracklist.get_consume().get() is False:
                self.core.tracklist.set_consume(True)
                return
            if self.core.tracklist.get_repeat().get() is True:
                self.core.tracklist.set_repeat(False)
                return
            if self.core.tracklist.get_random().get() is True:
                self.core.tracklist.set_random(False)
                return
            if self.core.tracklist.get_single().get() is True:
                self.core.tracklist.set_single(False)
                return

            self.setup_required = False

    def options_changed(self):
        self.setup_required = True
        self.set_options()

    @only_execute_for_pandora_uris
    def on_event(self, event, **kwargs):
        self.event_monitor.on_event(event, **kwargs)
        getattr(self, event)(**kwargs)

    def track_playback_started(self, tl_track):
        self.set_options()

    def track_playback_ended(self, tl_track, time_position):
        self.set_options()

    def track_playback_paused(self, tl_track, time_position):
        self.set_options()

    def track_playback_resumed(self, tl_track, time_position):
        self.set_options()

    def event_processed(self, track_uri, pandora_event):
        if pandora_event == 'delete_station':
            self.core.tracklist.clear()

    def is_end_of_tracklist_reached(self, track=None):
        length = self.core.tracklist.get_length().get()
        if length <= 1:
            return True
        if track:
            tl_track = self.core.tracklist.filter({'uri': [track.uri]}).get()[0]
            track_index = self.core.tracklist.index(tl_track).get()
        else:
            track_index = self.core.tracklist.index().get()

        return track_index == length - 1

    def is_station_changed(self, track):
        try:
            previous_track_uri = PandoraUri.factory(self.core.history.get_history().get()[1][1].uri)
            if previous_track_uri.station_id != PandoraUri.factory(track.uri).station_id:
                return True
        except (IndexError, NotImplementedError):
            # No tracks in history, or last played track was not a Pandora track. Ignore
            pass
        return False

    def track_changing(self, track):
        if self.is_station_changed(track):
            # Station has changed, remove tracks from previous station from tracklist.
            self._trim_tracklist(keep_only=track)
        if self.is_end_of_tracklist_reached(track):
            self._trigger_end_of_tracklist_reached(PandoraUri.factory(track).station_id,
                                                   auto_play=False)

    def track_unplayable(self, track):
        if self.is_end_of_tracklist_reached(track):
            self.core.playback.stop()
            self._trigger_end_of_tracklist_reached(PandoraUri.factory(track).station_id,
                                                   auto_play=True)

        self.core.tracklist.remove({'uri': [track.uri]})

    def next_track_available(self, track, auto_play=False):
        if track:
            self.add_track(track, auto_play)
        else:
            logger.warning('No more Pandora tracks available to play.')
            self.core.playback.stop()

    def skip_limit_exceeded(self):
        self.core.playback.stop()

    def add_track(self, track, auto_play=False):
        # Add the next Pandora track
        self.core.tracklist.add(uris=[track.uri])
        if auto_play:
            tl_tracks = self.core.tracklist.get_tl_tracks().get()
            self.core.playback.play(tlid=tl_tracks[-1].tlid)
        self._trim_tracklist(maxsize=2)

    def _trim_tracklist(self, keep_only=None, maxsize=2):
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        if keep_only:
            trim_tlids = [t.tlid for t in tl_tracks if t.track.uri != keep_only.uri]
            if len(trim_tlids) > 0:
                return self.core.tracklist.remove({'tlid': trim_tlids})
            else:
                return 0

        elif len(tl_tracks) > maxsize:
            # Only need two tracks in the tracklist at any given time, remove the oldest tracks
            return self.core.tracklist.remove(
                {'tlid': [tl_tracks[t].tlid for t in range(0, len(tl_tracks)-maxsize)]}
            )

    def _trigger_end_of_tracklist_reached(self, station_id, auto_play=False):
        listener.PandoraFrontendListener.send('end_of_tracklist_reached', station_id=station_id, auto_play=auto_play)
