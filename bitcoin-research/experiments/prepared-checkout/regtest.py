# SPDX-License-Identifier: GPL-3.0-only
"""Own-process Bitcoin regtest isolation for the checkout experiment.

Run with a local bitcoind binary. The harness only connects to its own fresh,
network-disabled regtest process. It never reads existing Bitcoin configuration.
All keys and coins are disposable regtest material.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, ProxyHandler


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Regtest:
    def __init__(self, binary: Path) -> None:
        self.binary = binary.resolve(strict=True)
        self.directory = Path(tempfile.mkdtemp(prefix="prepared-checkout-regtest-"))
        # Explicit empty config and a unique datadir prevent inheriting real wallets.
        self.config = self.directory / "isolated.conf"
        self.config.write_text("", encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.process: subprocess.Popen | None = None
        self.log = None
        self.opener = build_opener(ProxyHandler({}))
        self.stopped = False

    def start(self) -> None:
        self.log = (self.directory / "process.log").open("wb")
        command = [
            str(self.binary), "-regtest", "-server", "-networkactive=0",
            "-listen=0", "-listenonion=0", "-dnsseed=0", "-discover=0",
            "-connect=0", "-persistmempool=0", "-fallbackfee=0.0002",
            "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1",
            f"-rpcport={self.port}", f"-datadir={self.directory}",
            f"-conf={self.config}",
        ]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log, **options)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("The newly launched regtest process exited during startup")
            try:
                info = self.rpc("getblockchaininfo")
                require(info["chain"] == "regtest", "Refusing a non-regtest chain")
                network = self.rpc("getnetworkinfo")
                require(network["networkactive"] is False, "Networking must be disabled")
                require(network["connections"] == 0, "Unexpected network connection")
                return
            except (OSError, RuntimeError):
                time.sleep(0.1)
        raise TimeoutError("Regtest startup did not finish within 30 seconds")

    def rpc(self, method: str, *params, wallet: str | None = None):
        cookie = (self.directory / "regtest" / ".cookie").read_text().strip()
        auth = base64.b64encode(cookie.encode()).decode()
        route = "/" if wallet is None else "/wallet/" + quote(wallet, safe="")
        request = Request(
            f"http://127.0.0.1:{self.port}{route}",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                             "params": list(params)}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                result = json.load(response)
        except HTTPError as error:
            result = json.load(error)
        if result.get("error"):
            raise RuntimeError(f"{method}: {result['error']}")
        return result["result"]

    def stop(self) -> None:
        # Only stop the child this instance launched, authenticated by its cookie.
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                require(self.rpc("getblockchaininfo")["chain"] == "regtest", "Wrong chain")
                self.rpc("stop")
                self.process.wait(timeout=15)
            except (OSError, RuntimeError, AssertionError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=10)
        self.stopped = self.process.poll() is not None
        if self.log is not None:
            self.log.close()
