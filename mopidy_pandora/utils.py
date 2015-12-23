import json

from mopidy import httpclient

import requests

import mopidy_pandora


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


def format_proxy(proxy_config):
    if not proxy_config.get('hostname'):
        return None

    port = proxy_config.get('port', 80)
    if port < 0:
        port = 80

    template = '{hostname}:{port}'

    return template.format(hostname=proxy_config['hostname'], port=port)


def get_requests_session(proxy_config, user_agent):
    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({'http': proxy, 'https': proxy})
    session.headers.update({'user-agent': full_user_agent})

    return session


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
    def _do_rpc(cls, mopidy_config, method, params=None, queue=None):
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

        session = get_requests_session(
            proxy_config=mopidy_config['proxy'],
            user_agent='%s/%s' % (
                mopidy_pandora.Extension.dist_name,
                mopidy_pandora.__version__))

        json_data = json.loads(session.get('POST', cls.url, data=json.dumps(data),
                                           headers={'Content-Type': 'application/json'}).text)
        if queue is not None:
            queue.put(json_data['result'])

        return json_data['result']
