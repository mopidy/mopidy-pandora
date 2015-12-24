import Queue

import json

import logging

from mock import mock

import requests

from mopidy_pandora import utils
from mopidy_pandora.utils import run_async

logger = logging.getLogger(__name__)


def test_format_proxy():
    config = {
        'proxy': {
            'hostname': 'mock_host',
            'port': '8080'
        }
    }

    assert utils.format_proxy(config['proxy']) == 'mock_host:8080'


def test_format_proxy_no_hostname():
    config = {
        'proxy': {
            'hostname': '',
            'port': 'mock_port'
        }
    }

    assert utils.format_proxy(config['proxy']) is None
    config.pop('hostname')
    assert utils.format_proxy(config['proxy']) is None


def test_format_proxy_no_port():
    config = {
        'proxy': {
            'hostname': 'mock_host',
            'port': ''
        }
    }

    assert utils.format_proxy(config['proxy']) == 'mock_host:80'
    config.pop('port')
    assert utils.format_proxy(config['proxy']) == 'mock_host:80'


def test_rpc_client_uses_mopidy_defaults():
    assert utils.RPCClient.hostname == '127.0.0.1'
    assert utils.RPCClient.port == '6680'

    assert utils.RPCClient.url == 'http://127.0.0.1:6680/mopidy/rpc'


def test_do_rpc():
    utils.RPCClient.configure('mock_host', 'mock_port')
    assert utils.RPCClient.hostname == 'mock_host'
    assert utils.RPCClient.port == 'mock_port'

    response_mock = mock.PropertyMock(spec=requests.Response)
    response_mock.text = '{"result": "mock_result"}'
    requests.request = mock.PropertyMock(return_value=response_mock)

    q = Queue.Queue()
    utils.RPCClient._do_rpc('mock_method',
                            params={'mock_param_1': 'mock_value_1', 'mock_param_2': 'mock_value_2'},
                            queue=q)

    assert q.get() == 'mock_result'


def test_do_rpc_increments_id():
    requests.request = mock.PropertyMock()
    json.loads = mock.PropertyMock()

    current_id = utils.RPCClient.id
    t = utils.RPCClient._do_rpc('mock_method')
    t.join()
    assert utils.RPCClient.id == current_id + 1


def test_run_async(caplog):
    t = async_func('test_1_async')
    t.join()
    assert 'test_1_async' in caplog.text()


def test_run_async_queue(caplog):
    q = Queue.Queue()
    async_func('test_2_async', queue=q)
    assert 'test_2_async' in caplog.text()
    assert q.get() == 'test_value'


@run_async
def async_func(text, queue=None):
    logger.info(text)
    queue.put('test_value')
