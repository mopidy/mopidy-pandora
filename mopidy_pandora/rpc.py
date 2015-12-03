import Queue
import json

import requests


def run_async(func):
    """ Function decorator intended to make "func" run in a separate thread (asynchronously).

    :param func: the function to run asynchronously
    :return: the created Thread object that the function is running in.
    """

    from threading import Thread
    from functools import wraps

    @wraps(func)
    def async_func(*args, **kwargs):
        """ Run a function asynchronously

        :param args: all arguments will be passed to the target function
        :param kwargs: pass a Queue.Queue() object with the optional 'queue' keyword if you would like to retrieve
               the results after the thread has run. All other keyword arguments will be passed to the target function.
        :return: the created Thread object that the function is running in.
        """

        queue = kwargs.get('queue', None)

        t = Thread(target=func, args=args, kwargs=kwargs)
        t.start()

        if queue is not None:
            t.result_queue = queue

        return t

    return async_func


class RPCClient(object):
    hostname = '127.0.0.1'
    port = '6680'

    url = 'http://' + str(hostname) + ':' + str(port) + '/mopidy/rpc'
    id = 0

    @classmethod
    def configure(cls, hostname, port):
        cls.hostname = hostname
        cls.port = port

    @classmethod
    @run_async
    def _do_rpc(cls, method, params=None, queue=None):
        """ Makes an asynchronously remote procedure call to the Mopidy server.

        :param method: the name of the Mopidy remote procedure to be called (typically from the 'core' module.
        :param params: a dictionary of argument:value pairs to be passed directly to the remote procedure.
        :param queue: a Queue.Queue() object that the results of the thread should be stored in.
        :return: the 'result' element of the json results list returned by the remote procedure call.
        """

        cls.id += 1
        data = {'method': method, 'jsonrpc': '2.0', 'id': cls.id}

        if params is not None:
            data['params'] = params

        json_data = json.loads(requests.request('POST', cls.url, data=json.dumps(data),
                                                headers={'Content-Type': 'application/json'}).text)
        if queue is not None:
            queue.put(json_data['result'])

        return json_data['result']

    @classmethod
    def tracklist_set_repeat(cls, value=True, queue=None):
        return cls._do_rpc('core.tracklist.set_repeat', params={'value': value}, queue=queue)

    @classmethod
    def tracklist_set_consume(cls, value=True, queue=None):
        return cls._do_rpc('core.tracklist.set_consume', params={'value': value}, queue=queue)

    @classmethod
    def tracklist_set_single(cls, value=True, queue=None):
        return cls._do_rpc('core.tracklist.set_single', params={'value': value}, queue=queue)

    @classmethod
    def tracklist_set_random(cls, value=True, queue=None):
        return cls._do_rpc('core.tracklist.set_random', params={'value': value}, queue=queue)

    @classmethod
    def playback_resume(cls, queue=None):
        return cls._do_rpc('core.playback.resume', queue=queue)

    @classmethod
    def playback_stop(cls, queue=None):
        return cls._do_rpc('core.playback.stop', queue=queue)

    @classmethod
    def tracklist_previous_track(cls, tl_track, queue=None):
        return cls._do_rpc('core.tracklist.previous_track', params={'tl_track': tl_track}, queue=queue)

    @classmethod
    def playback_get_current_tl_track(cls, queue=None):
        return cls._do_rpc('core.playback.get_current_tl_track', queue=queue)

    @classmethod
    def tracklist_next_track(cls, tl_track, queue=None):
        return cls._do_rpc('core.tracklist.next_track', params={'tl_track': tl_track}, queue=queue)

    @classmethod
    def tracklist_index(cls, tl_track=None, tlid=None, queue=None):
        return cls._do_rpc('core.tracklist.index', params={'tl_track': tl_track, 'tlid': tlid},
                           queue=queue)

    @classmethod
    def tracklist_get_length(cls, queue=None):
        return cls._do_rpc('core.tracklist.get_length', queue=queue)

    @classmethod
    def tracklist_add(cls, tracks=None, at_position=None, uri=None, uris=None, queue=None):
        return cls._do_rpc('core.tracklist.add', params={'tracks': tracks, 'at_position': at_position,
                                                         'uri': uri, 'uris': uris}, queue=queue)
