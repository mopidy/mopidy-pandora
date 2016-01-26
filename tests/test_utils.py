from __future__ import absolute_import, division, print_function, unicode_literals

try:
    import queue
except ImportError:
    import Queue as queue

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
            'hostname': 'host_mock',
            'port': '8080'
        }
    }

    assert utils.format_proxy(config['proxy']) == 'host_mock:8080'


def test_format_proxy_no_hostname():
    config = {
        'proxy': {
            'hostname': '',
            'port': 'port_mock'
        }
    }

    assert utils.format_proxy(config['proxy']) is None
    config['proxy'].pop('hostname')
    assert utils.format_proxy(config['proxy']) is None


def test_format_proxy_no_port():
    config = {
        'proxy': {
            'hostname': 'host_mock',
            'port': ''
        }
    }

    assert utils.format_proxy(config['proxy']) == 'host_mock:80'
    config['proxy'].pop('port')
    assert utils.format_proxy(config['proxy']) == 'host_mock:80'


def test_rpc_client_uses_mopidy_defaults():
    assert utils.RPCClient.hostname == '127.0.0.1'
    assert utils.RPCClient.port == '6680'

    assert utils.RPCClient.url == 'http://127.0.0.1:6680/mopidy/rpc'


def test_do_rpc():
    utils.RPCClient.configure('host_mock', 'port_mock')
    assert utils.RPCClient.hostname == 'host_mock'
    assert utils.RPCClient.port == 'port_mock'

    response_mock = mock.PropertyMock(spec=requests.Response)
    response_mock.text = '{"result": "result_mock"}'
    requests.request = mock.PropertyMock(return_value=response_mock)

    q = queue.Queue()
    utils.RPCClient._do_rpc('method_mock',
                            params={'param_mock_1': 'value_mock_1', 'param_mock_2': 'value_mock_2'},
                            queue=q)

    assert q.get() == 'result_mock'


def test_do_rpc_increments_id():
    requests.request = mock.PropertyMock()
    json.loads = mock.PropertyMock()

    current_id = utils.RPCClient.id
    t = utils.RPCClient._do_rpc('method_mock')
    t.join()
    assert utils.RPCClient.id == current_id + 1


def test_run_async(caplog):
    t = async_func('test_1_async')
    t.join()
    assert 'test_1_async' in caplog.text()


def test_run_async_queue(caplog):
    q = queue.Queue()
    async_func('test_2_async', queue=q)
    assert q.get() == 'test_value'
    assert 'test_2_async' in caplog.text()


@run_async
def async_func(text, queue=None):
    logger.info(text)
    queue.put('test_value')
