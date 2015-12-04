import Queue

import threading

from mopidy.internal import encoding

from mopidy_pandora import logger, rpc


class PandoraTracklistProvider(object):

    def __init__(self, backend):

        self.backend = backend

        self.previous_tl_track = None
        self.current_tl_track = None
        self.next_tl_track = None

        self._tracklist_synced_event = threading.Event()

    @property
    def tracklist_is_synced(self):
        return self._tracklist_synced_event.get()

    def configure(self):
        # Setup tracklist to mirror behaviour of official Pandora front-ends.
        self.set_repeat(False)
        self.set_consume(True)
        self.set_random(False)
        self.set_single(False)

    def get_length(self, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.get_length', queue=queue)

    def set_random(self, value=True, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.set_random', params={'value': value}, queue=queue)

    def set_repeat(self, value=True, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.set_repeat', params={'value': value}, queue=queue)

    def set_single(self, value=True, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.set_single', params={'value': value}, queue=queue)

    def set_consume(self, value=True, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.set_consume', params={'value': value}, queue=queue)

    def index(self, tl_track=None, tlid=None, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.index', params={'tl_track': tl_track, 'tlid': tlid},
                                     queue=queue)

    def next_track(self, tl_track, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.next_track', params={'tl_track': tl_track}, queue=queue)

    def previous_track(self, tl_track, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.previous_track', params={'tl_track': tl_track}, queue=queue)

    def add(self, tracks=None, at_position=None, uri=None, uris=None, queue=Queue.Queue(1)):
        return rpc.RPCClient._do_rpc('core.tracklist.add', params={'tracks': tracks, 'at_position': at_position,
                                     'uri': uri, 'uris': uris}, queue=queue)

    def clear(self):
        raise NotImplementedError

    @rpc.run_async
    def sync(self):
        """ Sync the current tracklist information, and add more Pandora tracks to the tracklist as necessary.
        """
        self._tracklist_synced_event.clear()
        try:
            self.current_tl_track = self.backend.playback.get_current_tl_track().result_queue\
                .get(timeout=rpc.thread_timeout)

            tl_index = self.index(tlid=self.current_tl_track['tlid']).result_queue\
                .get(timeout=rpc.thread_timeout)

            tl_length = self.get_length().result_queue.get(timeout=rpc.thread_timeout)

            # TODO note that tlid's will be changed to start at '1' instead of '0' in the next release of Mopidy.
            # the following statement should change to 'if index >= length:' when that happens.
            # see https://github.com/mopidy/mopidy/commit/4c5e80a2790c6bea971b105f11ab3f7c16617173
            if tl_index >= tl_length-1:
                # We're at the end of the tracklist, add the next Pandora track
                track = self.backend.library.next_track()

                t = self.add(uris=[track.uri])
                t.join(rpc.thread_timeout*2)

            self.previous_tl_track = self.previous_track(self.current_tl_track).result_queue\
                .get(timeout=rpc.thread_timeout)

            self.next_tl_track = self.next_track(self.current_tl_track).result_queue\
                .get(timeout=rpc.thread_timeout)

            self._tracklist_synced_event.set()

        except Exception as e:
            logger.error('Error syncing tracklist: %s.', encoding.locale_decode(e))
            self.previous_tl_track = self.current_tl_track = self.next_tl_track = None
