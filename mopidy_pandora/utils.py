from __future__ import absolute_import, division, print_function, unicode_literals

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
        t = Thread(target=func, args=args, kwargs=kwargs)

        queue = kwargs.get('queue', None)
        if queue is not None:
            t.result_queue = queue

        t.start()
        return t

    return async_func


def format_proxy(proxy_config):
    if not proxy_config.get('hostname'):
        return None

    port = proxy_config.get('port')
    if not port or port < 0:
        port = 80

    template = '{hostname}:{port}'

    return template.format(hostname=proxy_config['hostname'], port=port)


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
        """
        cls.id += 1
        data = {'method': method, 'jsonrpc': '2.0', 'id': cls.id}

        if params is not None:
            data['params'] = params

        json_data = json.loads(requests.request('POST', cls.url, data=json.dumps(data),
                                                headers={'Content-Type': 'application/json'}).text)
        if queue is not None:
            queue.put(json_data['result'])
