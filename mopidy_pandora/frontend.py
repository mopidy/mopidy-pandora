import logging

import time

from mopidy import core
from mopidy.audio import PlaybackState

import pykka

from mopidy_pandora import listener
from mopidy_pandora.uri import AdItemUri, PandoraUri


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


class PandoraFrontendFactory(pykka.ThreadingActor):

    def __new__(cls, config, core):
        if config['pandora'].get('event_support_enabled'):
            return EventHandlingPandoraFrontend(config, core)
        else:
            return PandoraFrontend(config, core)


class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraBackendListener,
                      listener.PandoraPlaybackListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config['pandora']
        self.auto_setup = self.config.get('auto_setup')

        self.setup_required = True
        self.core = core

    def set_options(self):
        # Setup playback to mirror behaviour of official Pandora front-ends.
        if self.auto_setup and self.setup_required:
            assert isinstance(self.core.tracklist, object)
            if self.core.tracklist.get_repeat().get() is True:
                self.core.tracklist.set_repeat(False)
            if self.core.tracklist.get_consume().get() is False:
                self.core.tracklist.set_consume(True)
            if self.core.tracklist.get_random().get() is True:
                self.core.tracklist.set_random(False)
            if self.core.tracklist.get_single().get() is True:
                self.core.tracklist.set_single(False)

            self.setup_required = False

    def options_changed(self):
        self.setup_required = True

    @only_execute_for_pandora_uris
    def track_playback_started(self, tl_track):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_ended(self, tl_track, time_position):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_paused(self, tl_track, time_position):
        self.set_options()

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        self.set_options()

    def end_of_tracklist_reached(self, track=None):
        length = self.core.tracklist.get_length().get()
        if length <= 1:
            return True
        if track:
            tl_track = self.core.tracklist.filter({'uri': [track.uri]}).get()[0]
            index = self.core.tracklist.index(tl_track).get()
        else:
            index = self.core.tracklist.index().get()

        return index == length - 1

    def track_changed(self, track):
        if self.end_of_tracklist_reached(track):
            self._trigger_end_of_tracklist_reached(auto_play=False)

    def track_unplayable(self, track):
        if self.end_of_tracklist_reached(track):
            self.core.playback.stop()
            self._trigger_end_of_tracklist_reached(auto_play=True)
        self.core.tracklist.remove({'uri': [track.uri]}).get()

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
        self.core.tracklist.add(uris=[track.uri]).get()
        tl_tracks = self.core.tracklist.get_tl_tracks().get()
        if len(tl_tracks) > 2:
            # Only need two tracks in the tracklist at any given time, remove the oldest tracks
            self.core.tracklist.remove({'tlid': [tl_tracks[t].tlid for t in range(0, len(tl_tracks)-2)]}).get()
        if auto_play:
            self.core.playback.play(tl_tracks[-1]).get()

    def _trigger_end_of_tracklist_reached(self, auto_play=False):
        listener.PandoraFrontendListener.send('end_of_tracklist_reached', auto_play=auto_play)


class EventHandlingPandoraFrontend(PandoraFrontend, listener.PandoraEventHandlingPlaybackListener):

    def __init__(self, config, core):
        super(EventHandlingPandoraFrontend, self).__init__(config, core)

        self.settings = {
            'resume': config['pandora'].get('on_pause_resume_click'),
            'change_track_next': config['pandora'].get('on_pause_next_click'),
            'change_track_previous': config['pandora'].get('on_pause_previous_click'),
            'stop': config['pandora'].get('on_pause_stop_click')
        }

        self.double_click_interval = float(config['pandora'].get('double_click_interval'))
        self._click_time = 0

    @only_execute_for_pandora_uris
    def track_playback_paused(self, tl_track, time_position):
        super(EventHandlingPandoraFrontend, self).track_playback_paused(tl_track, time_position)
        if time_position > 0:
            self.set_click_time()

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        super(EventHandlingPandoraFrontend, self).track_playback_resumed(tl_track, time_position)
        self.check_doubleclicked(action='resume')

    def track_changed(self, track):
        super(EventHandlingPandoraFrontend, self).track_changed(track)
        self.check_doubleclicked(action='change_track')

    def set_click_time(self, click_time=None):
        if click_time is None:
            self._click_time = time.time()
        else:
            self._click_time = click_time

    def get_click_time(self):
        return self._click_time

    def check_doubleclicked(self, action=None):
        if self._is_double_click():
            self._process_event(action=action)

    def event_processed(self, track_uri, pandora_event):
        if pandora_event == 'delete_station':
            self.core.tracklist.clear()

    def _is_double_click(self):
        double_clicked = self._click_time > 0 and time.time() - self._click_time < self.double_click_interval
        self.set_click_time(0)

        return double_clicked

    def _process_event(self, action=None):
        try:
            event_target_uri, event_target_action = self._get_event_targets(action=action)

            if type(PandoraUri.factory(event_target_uri)) is AdItemUri:
                logger.info('Ignoring doubleclick event for Pandora advertisement...')
                return

            self._trigger_event_triggered(event_target_uri, event_target_action)
            # Resume playback...
            if action in ['stop', 'change_track'] and self.core.playback.get_state().get() != PlaybackState.PLAYING:
                self.core.playback.resume().get()
        except ValueError:
            logger.exception("Error processing Pandora event '{}', ignoring...".format(action))
            return

    def _get_event_targets(self, action=None):
        current_track_uri = self.core.playback.get_current_tl_track().get().track.uri

        if action == 'change_track':
            previous_track_uri = self.core.history.get_history().get()[1][1].uri
            if current_track_uri == previous_track_uri:
                # Replaying last played track, user clicked 'previous'.
                action = self.settings['change_track_previous']
            else:
                # Track not in recent tracklist history, user clicked 'next'.
                action = self.settings['change_track_next']

            return previous_track_uri, action

        elif action in ['resume', 'stop']:
            return current_track_uri, self.settings[action]

        raise ValueError('Unexpected event: {}'.format(action))

    def _trigger_event_triggered(self, track_uri, event):
        (listener.PandoraEventHandlingFrontendListener.send('event_triggered',
                                                            track_uri=track_uri,
                                                            pandora_event=event))
