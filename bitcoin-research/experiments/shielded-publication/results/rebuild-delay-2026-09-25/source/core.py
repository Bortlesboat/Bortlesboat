"""Owned regtest processes and exact-fee synthetic Bitcoin data carriers."""

import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


SATOSHIS = Decimal(100_000_000)
TRACE_METHODS = {
    'testmempoolaccept', 'sendrawtransaction', 'getrawmempool',
    'getmempoolentry', 'getblocktemplate', 'generatetoaddress', 'getblock',
    'getpeerinfo', 'addnode', 'getnetworkinfo', 'getblockchaininfo',
}


def json_text(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def file_sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


class RpcError(RuntimeError):
    def __init__(self, error: dict):
        self.code = error['code']
        self.message = error['message']
        super().__init__(f'RPC {self.code}: {self.message}')


class Node:
    """Start and stop only a process created by this instance, in a marked dir."""

    def __init__(
        self, binary: Path, data_dir: Path, *, carrier_limit: int = 100_000,
        listen: bool = False, trace: Path | None = None,
    ):
        self.binary = binary.resolve()
        self.data_dir = data_dir.resolve()
        self.trace_path = trace
        self.rpc_port, self.p2p_port = free_port(), free_port()
        self.carrier_limit, self.listen = carrier_limit, listen
        self.process = None
        self.log = None
        self.trace = None
        self.counter = 0
        self.stopped = False
        self.mock_time = 1_700_000_000
        self._rpc_opener = build_opener(ProxyHandler({}))

    def __enter__(self):
        marker = self.data_dir / '.publication-bench-owned'
        if self.data_dir.exists() and not marker.is_file():
            raise ValueError('refusing an existing unowned node data directory')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text('isolated regtest benchmark\n', encoding='ascii')
        clock = self.data_dir / 'benchmark-clock.txt'
        if clock.is_file():
            self.mock_time = int(clock.read_text(encoding='ascii'))
        config = self.data_dir / 'bitcoin.conf'
        config.write_text('# Isolated publication benchmark; no global config.\n', encoding='ascii')
        args = [
            str(self.binary), f'-datadir={self.data_dir}', f'-conf={config}',
            '-regtest=1', '-server=1', '-dnsseed=0', '-discover=0', '-connect=0',
            '-listenonion=0', '-natpmp=0', '-rpcbind=127.0.0.1',
            '-rpcallowip=127.0.0.1', f'-rpcport={self.rpc_port}',
            f'-listen={int(self.listen)}', f'-port={self.p2p_port}',
            '-acceptnonstdtxn=0',
            f'-datacarriersize={self.carrier_limit}', '-blockmaxweight=10000',
            '-blockreservedweight=2000', '-blockmintxfee=0.00001',
            '-minrelaytxfee=0.00001', '-incrementalrelayfee=0.00001',
            '-fallbackfee=0.00001', '-dbcache=64', '-par=1',
            '-rpcthreads=2', f'-mocktime={self.mock_time}',
        ]
        if self.listen:
            args.append('-bind=127.0.0.1')
        self.log = (self.data_dir / 'process.log').open('wb')
        if self.trace_path:
            self.trace = self.trace_path.open('w', encoding='utf-8')
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        try:
            self.process = subprocess.Popen(args, stdout=self.log, stderr=self.log, creationflags=flags)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f'owned node exited; inspect {self.data_dir / "process.log"}')
                try:
                    chain = self.call('getblockchaininfo')
                    if chain['chain'] != 'regtest':
                        raise RuntimeError('refusing a non-regtest RPC endpoint')
                    version = self.call('getnetworkinfo')['version']
                    if version != 310100:
                        raise RuntimeError(f'expected Core 31.1 (310100), got {version}')
                    return self
                except (OSError, URLError):
                    time.sleep(0.1)
                except RpcError as error:
                    if error.code != -28:
                        raise
                    time.sleep(0.1)
            raise TimeoutError('owned regtest node did not become ready')
        except BaseException:
            self.close()
            raise

    def call(self, method: str, *params, wallet: bool = False):
        self.counter += 1
        body = {'jsonrpc': '2.0', 'id': self.counter, 'method': method, 'params': list(params)}
        cookie = (self.data_dir / 'regtest' / '.cookie').read_text(encoding='ascii').strip()
        authorization = base64.b64encode(cookie.encode()).decode()
        endpoint = f'http://127.0.0.1:{self.rpc_port}' + ('/wallet/lab' if wallet else '/')
        request = Request(endpoint, json_text(body).encode(), {
            'Authorization': f'Basic {authorization}', 'Content-Type': 'application/json',
        })
        try:
            with self._rpc_opener.open(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as error:
            raw = error.read()
        decoded = json.loads(raw, parse_float=Decimal)
        if self.trace and method in TRACE_METHODS:
            self.trace.write(json_text({'request': body, 'response': decoded}) + '\n')
            self.trace.flush()
        if decoded.get('error'):
            raise RpcError(decoded['error'])
        if method == 'setmocktime':
            self.mock_time = params[0]
        return decoded['result']

    def ensure_wallet(self) -> None:
        if 'lab' not in self.call('listwallets'):
            self.call('loadwallet', 'lab')

    def mine(self, address: str, count: int = 1) -> list[str]:
        hashes = []
        for _ in range(count):
            height = self.call('getblockcount') + 1
            self.call('setmocktime', 1_700_000_000 + height * 600)
            hashes.extend(self.call('generatetoaddress', 1, address))
        return hashes

    def close(self) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.call('stop')
                except (OSError, URLError, RpcError, ValueError):
                    pass
                try:
                    self.process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    # Popen retains the handle of our own child, not a name/PID search.
                    self.process.terminate()
                    self.process.wait(timeout=10)
            self.stopped = self.process is None or self.process.poll() is not None
        finally:
            if (self.data_dir / '.publication-bench-owned').is_file():
                (self.data_dir / 'benchmark-clock.txt').write_text(str(self.mock_time), encoding='ascii')
            if self.trace:
                self.trace.close()
            if self.log:
                self.log.close()

    def __exit__(self, *_):
        self.close()


def build_carrier(node: Node, utxo: dict, address: str, payload: bytes, rate: int) -> dict:
    """One fixed P2TR funding input, one P2TR change output, one OP_RETURN.

    Sign a provisional transaction to obtain actual vsize, then set the exact
    integer fee and sign again. Taproot's fixed signature length keeps size fixed.
    """
    input_sats = int(Decimal(utxo['amount']) * SATOSHIS)
    inputs = [{'txid': utxo['txid'], 'vout': utxo['vout'], 'sequence': 0xFFFFFFFD}]

    def signed(fee_sats: int) -> tuple[str, dict]:
        if not 0 < fee_sats < input_sats:
            raise ValueError('fee must be positive and below the synthetic input amount')
        change = format(Decimal(input_sats - fee_sats) / SATOSHIS, '.8f')
        raw = node.call('createrawtransaction', inputs, [{address: change}, {'data': payload.hex()}])
        result = node.call('signrawtransactionwithwallet', raw, wallet=True)
        if not result['complete']:
            raise RuntimeError('synthetic carrier signing incomplete')
        return result['hex'], node.call('decoderawtransaction', result['hex'])

    _, provisional = signed(1000)
    fee_sats = provisional['vsize'] * rate
    raw, decoded = signed(fee_sats)
    if decoded['vsize'] != provisional['vsize']:
        raise RuntimeError('signed transaction size changed while setting exact fee')
    outputs_sats = sum(int(v['value'] * SATOSHIS) for v in decoded['vout'])
    if input_sats - outputs_sats != fee_sats:
        raise RuntimeError('decoded outputs disagree with exact fee')
    return {
        'txid': decoded['txid'], 'hex': raw, 'vsize': decoded['vsize'],
        'weight': decoded['weight'], 'fee_sats': fee_sats, 'rate_sat_vb': rate,
        'payload_hex': payload.hex(), 'funding_outpoint': inputs[0],
        'op_return_script_bytes': len(decoded['vout'][1]['scriptPubKey']['hex']) // 2,
    }


def submit(node: Node, transaction: dict) -> dict:
    admission = node.call('testmempoolaccept', [transaction['hex']])[0]
    if not admission.get('allowed'):
        raise RuntimeError(f'carrier unexpectedly rejected: {admission}')
    txid = node.call('sendrawtransaction', transaction['hex'])
    if txid != transaction['txid']:
        raise RuntimeError('submitted txid differs from the decoded transaction')
    return admission
