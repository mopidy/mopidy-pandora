import json

import requests


class RPCClient(object):
    def __init__(self, hostname, port):

        self.url = 'http://' + str(hostname) + ':' + str(port) + '/mopidy/rpc'
        self.id = 0

    def _do_rpc(self, method, params=None):

        self.id += 1
        data = {'method': method, 'jsonrpc': '2.0', 'id': self.id}
        if params is not None:
            data['params'] = params

        return requests.request('POST', self.url, data=json.dumps(data), headers={'Content-Type': 'application/json'})

    def set_repeat(self):

        self._do_rpc('core.tracklist.set_repeat', {'value': True})

    def get_current_track_uri(self):

        response = self._do_rpc('core.playback.get_current_tl_track')
        return response.json()['result']['track']['uri']
