import threading

from mopidy import core

import pykka

from mopidy_pandora import listener, logger
from mopidy_pandora.uri import AdItemUri, PandoraUri


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
            # Ask Mopidy for the currently playing track
            active_uri = self.core.playback.get_current_tl_track().get().track.uri
        except AttributeError:
            # None available, try kwargs
            try:
                active_uri = kwargs['tl_track'].track.uri
            except KeyError:
                # Not there either, see if it was passed as the first argument
                try:
                    if type(args[0]) is TlTrack:
                        active_uri = args[0].track.uri
                except IndexError:
                    # Giving up
                    return None

        try:
            PandoraUri.parse(active_uri)
            return func(self, *args, **kwargs)
        except (NotImplementedError) as e:
            # Not playing a Pandora track. Don't do anything.
            logger.info('Not a Pandora track: ({}, {})'.format(func.func_name, encoding.locale_decode(e)))
            pass

    return check_pandora


def is_pandora_uri(active_uri):
    return active_uri and active_uri.startswith('pandora:')


class PandoraFrontend(pykka.ThreadingActor, core.CoreListener, listener.PandoraListener):

    def __init__(self, config, core):
        super(PandoraFrontend, self).__init__()

        self.config = config
        self.auto_setup = self.config.get('auto_setup', True)

        self.setup_required = True
        self.core = core

    @only_execute_for_pandora_uris
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

    def prepare_tracklist(self, track, auto_play):
        tl_tracks = self.core.tracklist.add(uris=[track.uri])
        if auto_play:
            self.core.playback.play(tl_tracks.get()[0])

    def _trigger_prepare_next_track(self, auto_play):
        listener.PandoraListener.send('prepare_next_track', auto_play=auto_play)


class EventSupportPandoraFrontend(PandoraFrontend):

    def __init__(self, config, core):
        super(EventSupportPandoraFrontend, self).__init__(config, core)

        self.settings = {
            'OPR_EVENT': config.get('on_pause_resume_click', 'thumbs_up'),
            'OPN_EVENT': config.get('on_pause_next_click', 'thumbs_down'),
            'OPP_EVENT': config.get('on_pause_previous_click', 'sleep')
        }

        self.previous_tl_track = None
        self.current_tl_track = None
        self.next_tl_track = None

        self.event_processed_event = threading.Event()
        self.event_processed_event.set()

        self.tracklist_changed_event = threading.Event()
        self.tracklist_changed_event.set()

    @only_execute_for_pandora_uris
    def tracklist_changed(self):

        if not self.event_processed_event.isSet():
            # Delay 'tracklist_changed' events until all events have been processed.
            self.tracklist_changed_event.clear()
        else:
            self.current_tl_track = self.core.playback.get_current_tl_track().get()
            self.previous_tl_track = self.core.tracklist.previous_track(self.current_tl_track).get()
            self.next_tl_track = self.core.tracklist.next_track(self.current_tl_track).get()

            self.tracklist_changed_event.set()

    @only_execute_for_pandora_uris
    def track_playback_resumed(self, tl_track, time_position):
        super(EventSupportPandoraFrontend, self).track_playback_resumed(tl_track, time_position)

        self._process_events(tl_track.track.uri, time_position)

    def _process_events(self, track_uri, time_position):

        # Check if there are any events that still require processing.
        if self.event_processed_event.isSet():
            # No events to process.
            return

        event_target_uri = self._get_event_target_uri(track_uri, time_position)

        if type(PandoraUri.parse(event_target_uri)) is AdItemUri:
            logger.info('Ignoring doubleclick event for advertisement')
            self.event_processed_event.set()
            return

        event = self._get_event(track_uri, time_position)

        assert event_target_uri and event
        self._trigger_call_event(event_target_uri, event)

    def _get_event_target_uri(self, track_uri, time_position):
        if time_position == 0:
            # Track was just changed, trigger the event for the previously played track.
            history = self.core.history.get_history().get()
            return history[1][1].uri
        else:
            # Trigger the event for the track that is playing currently.
            return track_uri

    def _get_event(self, track_uri, time_position):
        if track_uri == self.previous_tl_track.track.uri:
            if time_position > 0:
                # Resuming playback on the first track in the tracklist.
                return self.settings['OPR_EVENT']
            else:
                return self.settings['OPP_EVENT']

        elif track_uri == self.current_tl_track.track.uri:
            return self.settings['OPR_EVENT']

        elif track_uri == self.next_tl_track.track.uri:
            return self.settings['OPN_EVENT']

    def event_processed(self, track_uri):
        self.event_processed_event.set()

        if not self.tracklist_changed_event.isSet():
            # Do any 'tracklist_changed' updates that are pending.
            self.tracklist_changed()

    def doubleclicked(self):
        self.event_processed_event.clear()
        # Resume playback of the next track so long...
        self.core.playback.resume()

    def _trigger_call_event(self, track_uri, event):
        listener.PandoraListener.send('call_event', track_uri=track_uri, pandora_event=event)
