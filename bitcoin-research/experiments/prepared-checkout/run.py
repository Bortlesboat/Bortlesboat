# SPDX-License-Identifier: GPL-3.0-only
"""Reproduce ordinary Bitcoin checkout after a pinned A2L happy path.

Run on Linux (including WSL) with Python 3.10+, Cargo, Git, a C toolchain,
Clang/libclang, GMP headers, make, m4 and Bison. No system packages are installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from checkout import run
from regtest import require

HERE = Path(__file__).resolve().parent
UPSTREAM = "https://github.com/comit-network/a2l-poc.git"
COMMIT = "a261027f4bdb2384f715efa3f634d5796fe95019"
TRANSACTION_SHA256 = "bd6258e14072cd255ccd75ca15e3ae859a8480f62f9d28616d3133bbcd616dfc"

ADMISSION = r'''
        let before: SerdeValue = rpc_command(&self.bitcoind_url,
            ureq::json!({"jsonrpc":"1.0", "method":"testmempoolaccept", "params":[[hex]]}))?;
        let tip: u32 = rpc_command(&self.bitcoind_url,
            ureq::json!({"jsonrpc":"1.0", "method":"getblockcount", "params":[]}))?;
        anyhow::ensure!(message.lock_time == 0, "Only the completed-payment path is in scope");
        anyhow::ensure!(before[0]["allowed"] == true, "Transaction rejected: {}", before);
        println!("A2L_LAB_PREFLIGHT {}", ureq::json!({"txid":message.txid().to_string(),
            "tip_height":tip, "locktime":message.lock_time,
            "sequences":message.input.iter().map(|i| i.sequence).collect::<Vec<_>>(),
            "allowed":before[0]["allowed"]}));
        println!("A2L_LAB_TX {}", ureq::json!({"txid":message.txid().to_string(),
            "locktime":message.lock_time, "before":before[0], "ready":before[0]}));
'''


def replace_once(text: str, old: str, new: str, count: int = 1) -> str:
    require(text.count(old) == count, f"Unexpected pinned source shape: {old[:60]}")
    return text.replace(old, new)


def adapt_test(source: str) -> str:
    """Retain upstream happy-path balance assertions; replace only its node adapter."""
    start = source.index("#[test]\nfn e2e_refund()")
    end = source.index("struct E2EActor", start)
    adapted = source[:start] + source[end:]
    adapted = replace_once(adapted, "use harness::{run_happy_path, run_refund};", "use harness::run_happy_path;")
    adapted = replace_once(adapted,
        "use testcontainers::{clients, images::coblox_bitcoincore::BitcoinCore, Container, Docker};\n", "")
    adapted = replace_once(adapted,
        "    let client = clients::Cli::default();\n\n    let blockchain = BitcoindBlockchain::new(&client)?;",
        "    let blockchain = BitcoindBlockchain::new()?;")
    start = adapted.index("struct BitcoindBlockchain<'c>")
    end = adapted.index("impl Transition<bitcoin::Transaction>", start)
    adapted = adapted[:start] + (HERE / "launcher.rs.txt").read_text() + adapted[end:]
    adapted = replace_once(adapted, "for BitcoindBlockchain<'_>", "for BitcoindBlockchain")
    adapted = replace_once(adapted, '"{}/wallet/"', '"{}/wallet/lab_funder"', count=3)
    return replace_once(adapted, "        let hex = &serialize_hex(&message);",
                        "        let hex = &serialize_hex(&message);\n" + ADMISSION)


def fresh_directory(requested: Path | None) -> Path:
    """Never overwrite or reuse a caller's existing directory, even if empty."""
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="prepared-checkout-build-"))
    requested.mkdir(parents=True, exist_ok=False)
    return requested.resolve()


def main(binary: Path, requested: Path | None) -> None:
    require(platform.system() == "Linux", "Use Linux or WSL; native Windows/macOS are untested")
    binary = binary.expanduser().resolve(strict=True)
    require(binary.is_file() and os.access(binary, os.X_OK), "--bitcoind must be an executable file")
    cargo = Path.home() / ".cargo/bin/cargo"
    if not cargo.is_file():
        located = shutil.which("cargo")
        require(located is not None, "Install Cargo before running the experiment")
        cargo = Path(located)
    for tool in ("git", "cc", "clang", "make", "m4", "bison"):
        require(shutil.which(tool) is not None, f"Missing prerequisite: {tool}; see README")
    env = {**os.environ, "CARGO_BUILD_JOBS": "2", "CARGO_NET_GIT_FETCH_WITH_CLI": "true"}
    env["PATH"] = str(cargo.parent) + os.pathsep + env.get("PATH", "")
    root = fresh_directory(requested)
    # Override environment and Cargo config paths; downloaded sources may be cached.
    env["CARGO_TARGET_DIR"] = str(root / "target")
    env["CARGO_BUILD_BUILD_DIR"] = str(root / "build")
    artifacts = root / "results"
    artifacts.mkdir()
    print(f"Experiment workspace: {root}", flush=True)
    upstream = root / "upstream"
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", UPSTREAM, str(upstream)], check=True, timeout=180)
    subprocess.run(["git", "-C", str(upstream), "-c", "advice.detachedHead=false", "checkout", "--quiet", COMMIT],
                   check=True, timeout=60)
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    require(actual == COMMIT, "Wrong source revision")
    work = root / "work"
    shutil.copytree(upstream, work, ignore=shutil.ignore_patterns(".git"))
    require(hashlib.sha256((work / "src/bitcoin.rs").read_bytes()).hexdigest() == TRANSACTION_SHA256,
            "Unexpected upstream transaction constructor")
    for filename in ("Cargo.toml", "Cargo.lock"):
        target = work / filename
        original = target.read_text()
        changed = original.replace("http://github.com/LLFourn/class", "https://github.com/LLFourn/class")
        require(changed != original, f"Missing expected dependency transport in {filename}")
        target.write_text(changed)
        (artifacts / (filename + ".patch")).write_text("".join(difflib.unified_diff(
            original.splitlines(keepends=True), changed.splitlines(keepends=True),
            fromfile="upstream/" + filename, tofile="work/" + filename)))
    original = (upstream / "tests/e2e.rs").read_text()
    adapted = adapt_test(original)
    (work / "tests/community_checkout.rs").write_text(adapted)
    (artifacts / "core-adapter.patch").write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), adapted.splitlines(keepends=True),
        fromfile="upstream/tests/e2e.rs", tofile="work/tests/community_checkout.rs")))
    provenance = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_url": UPSTREAM, "upstream_commit": COMMIT,
        "platform": platform.system(), "machine": platform.machine(),
        "python": platform.python_version(),
        "cargo": subprocess.check_output([str(cargo), "--version"], text=True).strip(),
        "bison": subprocess.check_output(["bison", "--version"], text=True).splitlines()[0],
        "cargo_lock_sha256": hashlib.sha256((work / "Cargo.lock").read_bytes()).hexdigest(),
        "source_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".txt")},
        "fresh_upstream_clone": True, "fresh_compiled_target": True,
        "build_outputs_inside_fresh_workspace": True,
        "cargo_download_cache_may_be_reused": True,
        "scope": "Completed-payment path only; no refund, abort or anonymity evaluation.",
    }
    (artifacts / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Building the pinned prototype; this can take several minutes. Output: results/build.log", flush=True)
    with (artifacts / "build.log").open("w") as log:
        subprocess.run([str(cargo), "test", "--locked", "--release", "--test", "community_checkout", "--no-run"],
                       cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
    run(work, artifacts, binary, env, cargo)
    print(f"Results: {artifacts / 'results.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", type=Path, required=True, help="Path to a locally installed bitcoind executable")
    parser.add_argument("--work-dir", type=Path, help="New directory for source, build and results; defaults to a fresh temporary directory")
    args = parser.parse_args()
    main(args.bitcoind, args.work_dir)
