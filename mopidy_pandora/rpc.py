import Queue
import json
from threading import Thread

import requests


class RPCClient(object):
    hostname = '127.0.0.1'
    port = '6680'

    url = 'http://' + str(hostname) + ':' + str(port) + '/mopidy/rpc'
    id = 0

    previous_tlid_queue = Queue.Queue()
    current_tlid_queue = Queue.Queue()
    next_tlid_queue = Queue.Queue()

    @classmethod
    def configure(cls, hostname, port):
        cls.hostname = hostname
        cls.port = port

    @classmethod
    def _do_rpc(cls, *args, **kwargs):

        method = args[0]

        cls.id += 1
        data = {'method': method, 'jsonrpc': '2.0', 'id': cls.id}

        params = kwargs.get('params')
        if params is not None:
            data['params'] = params

        json_data = json.loads(requests.request('POST', cls.url, data=json.dumps(data),
                                                headers={'Content-Type': 'application/json'}).text)
        queue = kwargs.get('queue')
        if queue is not None:
            queue.put(json_data['result'])
            return queue
        else:
            return json_data['result']

    @classmethod
    def _start_thread(cls, *args, **kwargs):

        queue = kwargs.get('queue', None)

        t = Thread(target=cls._do_rpc, args=args, kwargs=kwargs)
        t.start()
        if queue is not None:
            t.result_queue = queue

        return t

    @classmethod
    def core_tracklist_set_repeat(cls, value=True, queue=None):
        return cls._start_thread('core.tracklist.set_repeat', params={'value': value}, queue=queue)

    @classmethod
    def core_tracklist_set_consume(cls, value=True, queue=None):
        return cls._start_thread('core.tracklist.set_consume', params={'value': value}, queue=queue)

    @classmethod
    def core_tracklist_set_single(cls, value=True, queue=None):
        return cls._start_thread('core.tracklist.set_single', params={'value': value}, queue=queue)

    @classmethod
    def core_tracklist_set_random(cls, value=True, queue=None):
        return cls._start_thread('core.tracklist.set_random', params={'value': value}, queue=queue)

    @classmethod
    def core_playback_resume(cls, queue=None):
        return cls._start_thread('core.playback.resume', queue=queue)

    @classmethod
    def core_playback_stop(cls, queue=None):
        return cls._start_thread('core.playback.stop', queue=queue)

    # @classmethod
    # def core_tracklist_get_length(cls, queue=None):
    #     return cls._start_thread('core.tracklist.get_length', queue=queue)

    @classmethod
    def core_tracklist_get_next_tlid(cls, queue=None):
        return cls._start_thread('core.tracklist.get_next_tlid', queue=queue)

    @classmethod
    def core_tracklist_get_previous_tlid(cls, queue=None):
        return cls._start_thread('core.tracklist.get_previous_tlid', queue=queue)

    @classmethod
    def core_playback_get_current_tlid(cls, queue=None):
        return cls._start_thread('core.playback.get_current_tlid', queue=queue)

    # @classmethod
    # def core_playback_get_current_tl_track(cls, queue=None):
    #     return cls._start_thread('core.playback.get_current_tl_track', queue=queue)

    @classmethod
    def core_tracklist_index(cls, tl_track=None, tlid=None, queue=None):
        return cls._start_thread('core.tracklist.index', params={'tl_track': tl_track, 'tlid': tlid},
                                 queue=queue)

    @classmethod
    def core_tracklist_get_length(cls, queue=None):
        return cls._start_thread('core.tracklist.get_length', queue=queue)

    @classmethod
    def core_tracklist_add(cls, tracks=None, at_position=None, uri=None, uris=None, queue=None):
        return cls._start_thread('core.tracklist.add', params={'tracks': tracks, 'at_position': at_position,
                                                               'uri': uri, 'uris': uris}, queue=queue)
