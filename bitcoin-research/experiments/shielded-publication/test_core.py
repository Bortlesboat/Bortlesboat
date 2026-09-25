"""RPC isolation checks using synthetic cookies and a captured HTTP transport."""

import base64
from decimal import Decimal
from email.message import Message
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import urllib.request
from urllib.response import addinfourl

from core import Node, RpcError


def response(raw: bytes, status: int = 200):
    result = addinfourl(BytesIO(raw), Message(), '', status)
    result.reason = 'OK' if status == 200 else 'Internal Server Error'
    return result


class RpcTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='publication-rpc-test-')
        self.addCleanup(temporary.cleanup)
        data_dir = Path(temporary.name)
        (data_dir / 'regtest').mkdir()
        self.cookie = data_dir / 'regtest' / '.cookie'
        self.cookie.write_text('synthetic:first\n', encoding='ascii')

        self.enterContext(patch.dict(os.environ, {
            'http_proxy': 'http://proxy.invalid:3128',
        }, clear=True))
        self.enterContext(patch('urllib.request.proxy_bypass', return_value=False))
        self.enterContext(patch('urllib.request._opener', None))
        # Keep urllib's proxy and HTTP handlers; stop before any socket transport.
        self.connection = Mock(sock=None)
        self.transport = self.enterContext(patch(
            'urllib.request.http.client.HTTPConnection', return_value=self.connection,
        ))
        self.enterContext(patch('core.free_port', side_effect=[18443, 18444]))
        self.node = Node(data_dir / 'unused-bitcoind', data_dir)

    def test_call_bypasses_proxy_and_preserves_wallet_rpc(self):
        self.connection.getresponse.side_effect = [
            response(b'{}'),
            response(b'{"result":{"amount":0.00000001},"error":null,"id":1}'),
        ]
        # Prove the configured proxy is active in this same no-network harness.
        with urllib.request.urlopen('http://127.0.0.1:18443/') as probe:
            probe.read()
        self.assertEqual(self.transport.call_args.args[0], 'proxy.invalid:3128')
        self.transport.reset_mock()
        self.connection.request.reset_mock()

        result = self.node.call('getmempoolentry', 'synthetic-txid', wallet=True)

        self.transport.assert_called_once_with('127.0.0.1:18443', timeout=15)
        method, endpoint, body, headers = self.connection.request.call_args.args
        self.assertEqual(method, 'POST')
        self.assertEqual(endpoint, '/wallet/lab')
        self.assertEqual(json.loads(body), {
            'jsonrpc': '2.0', 'id': 1, 'method': 'getmempoolentry',
            'params': ['synthetic-txid'],
        })
        self.assertEqual(headers['Authorization'],
                         'Basic ' + base64.b64encode(b'synthetic:first').decode())
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertEqual(result, {'amount': Decimal('0.00000001')})

    def test_each_call_rereads_cookie_and_traces_only_allowed_methods(self):
        self.connection.getresponse.side_effect = [
            response(b'{"result":{"chain":"regtest"},"error":null,"id":1}'),
            response(b'{"result":{"walletname":"lab"},"error":null,"id":2}'),
        ]
        self.node.trace = StringIO()

        self.node.call('getblockchaininfo')
        self.cookie.write_text('synthetic:rotated\n', encoding='ascii')
        self.node.call('getwalletinfo', wallet=True)

        first, second = self.connection.request.call_args_list
        self.assertEqual(first.args[1], '/')
        self.assertEqual(second.args[1], '/wallet/lab')
        self.assertEqual(json.loads(first.args[2])['id'], 1)
        self.assertEqual(json.loads(second.args[2])['id'], 2)
        for request, cookie in [(first, b'synthetic:first'), (second, b'synthetic:rotated')]:
            self.assertEqual(request.args[3]['Authorization'],
                             'Basic ' + base64.b64encode(cookie).decode())
        entries = [json.loads(line) for line in self.node.trace.getvalue().splitlines()]
        self.assertEqual(entries, [{
            'request': {'jsonrpc': '2.0', 'id': 1, 'method': 'getblockchaininfo', 'params': []},
            'response': {'result': {'chain': 'regtest'}, 'error': None, 'id': 1},
        }])

    def test_http_rpc_errors_preserve_code_and_message(self):
        self.connection.getresponse.return_value = response(
            b'{"result":null,"error":{"code":-26,"message":"synthetic rejection"},"id":1}',
            status=500,
        )

        with self.assertRaises(RpcError) as raised:
            self.node.call('sendrawtransaction', 'synthetic-transaction')

        self.assertEqual(raised.exception.code, -26)
        self.assertEqual(raised.exception.message, 'synthetic rejection')
        self.assertEqual(str(raised.exception), 'RPC -26: synthetic rejection')


if __name__ == '__main__':
    unittest.main()
