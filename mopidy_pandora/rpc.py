import Queue
import json
from threading import Thread

import requests


# def run_in_thread(fn):
#     def run(*k, **kw):
#         t = Thread(target=fn, args=k, kwargs=kw)
#         t.start()
#         return t
#     return run

previous_tlid_queue = Queue.Queue()
next_tlid_queue = Queue.Queue()


# def threaded(fn):
#
#     def wrapped_f(*args, **kwargs):
#         '''this function calls the decorated function and puts the
#         result in a queue'''
#         ret = fn(*args, **kwargs)
#         previous_tlid_queue.put(ret)
#
#     def wrap(*args, **kwargs):
#         '''this is the function returned from the decorator. It fires off
#         wrapped_f in a new thread and returns the thread object with
#         the result queue attached'''
#
#         t = Thread(target=wrapped_f, args=args, kwargs=kwargs)
#         t.daemon = False
#         t.start()
#         t.result_queue = Queue.Queue()
#         return t
#
#     return wrap


class RPCClient(object):
    def __init__(self, hostname, port):

        self.url = 'http://' + str(hostname) + ':' + str(port) + '/mopidy/rpc'
        self.id = 0

    def _do_rpc(self, *args, **kwargs):

        method = args[0]

        self.id += 1
        data = {'method': method, 'jsonrpc': '2.0', 'id': self.id}

        params = kwargs.get('params')
        if params is not None:
            data['params'] = params

        json_data = json.loads(requests.request('POST', self.url, data=json.dumps(data),
                                                headers={'Content-Type': 'application/json'}).text)
        queue = kwargs.get('queue')
        if queue is not None:
            queue.put(json_data['result'])
        else:
            return json_data['result']

    def _do_threaded_rpc(self, *args, **kwargs):

        t = Thread(target=self._do_rpc, args=args, kwargs=kwargs)
        t.start()

        queue = kwargs.get('queue')

        if queue is not None:
            t.result_queue = queue

        return t

    def set_repeat(self, value=True):
        return self._do_threaded_rpc('core.tracklist.set_repeat', params={'value': value})

    def set_consume(self, value=True):
        return self._do_threaded_rpc('core.tracklist.set_consume', params={'value': value})

    def set_single(self, value=True):
        return self._do_threaded_rpc('core.tracklist.set_single', params={'value': value})

    def set_random(self, value=True):
        return self._do_threaded_rpc('core.tracklist.set_random', params={'value': value})

    def resume_playback(self):
        return self._do_threaded_rpc('core.playback.resume')

    def stop_playback(self):
        return self._do_threaded_rpc('core.playback.stop')

    def tracklist_add(self, tracks):
        return self._do_threaded_rpc('core.tracklist.add', params={'tracks': tracks})

    def tracklist_get_length(self):
        return self._do_threaded_rpc('core.tracklist.get_length')

    def tracklist_get_next_tlid(self):
        return self._do_threaded_rpc('core.tracklist.get_next_tlid', queue=next_tlid_queue)

    def tracklist_get_previous_tlid(self):
        return self._do_threaded_rpc('core.tracklist.get_previous_tlid', queue=previous_tlid_queue)

    def get_current_tlid(self):
        return self._do_threaded_rpc('core.playback.get_current_tlid')

    def get_current_tl_track(self):
        return self._do_threaded_rpc('core.playback.get_current_tl_track')
