import json

import requests


class RPCClient(object):
    def __init__(self, hostname, port):

        self.url = 'http://' + str(hostname) + ':' + str(port) + '/mopidy/rpc'
        self.id = 0

    def set_repeat(self):

        self.id += 1
        params = {'method': 'core.tracklist.set_repeat', 'params': {'value': True}, 'jsonrpc': '2.0', 'id': self.id}

        requests.request('POST', self.url, data=json.dumps(params), headers={'Content-Type': 'application/json'})
