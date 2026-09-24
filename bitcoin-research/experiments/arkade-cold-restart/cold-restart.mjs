// SPDX-License-Identifier: MIT
// Copy into packages/ts-sdk/ in the pinned upstream checkout; see README.md.
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { EventSource } from "eventsource";
import {
    EsploraProvider,
    OnchainWallet,
    ProviderUnavailableError,
    SingleKey,
    UnilateralExit,
    Wallet,
    configureEventSource,
    deserializeExitPackage,
    serializeExitPackage,
} from "./dist/index.js";
import {
    SQLiteContractRepository,
    SQLiteVirtualTxRepository,
    SQLiteWalletRepository,
} from "./dist/repositories/sqlite/index.js";

const revision = "8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1";
configureEventSource((url) => new EventSource(url));
const [phase, directory] = process.argv.slice(2);
assert(["seed", "missing", "prepare", "execute", "spend"].includes(phase));
assert(directory, "A separate experiment directory is required");
const dir = resolve(directory);
const arkUrl = process.env.RECOVERY_ARK_URL ?? "http://127.0.0.1:7070";
const esploraUrl = process.env.RECOVERY_ESPLORA_URL ?? "http://127.0.0.1:3000/api";
for (const value of [arkUrl, esploraUrl]) {
    const url = new URL(value);
    assert.equal(url.protocol, "http:");
    assert(["localhost", "127.0.0.1"].includes(url.hostname), "Local regtest endpoints only");
    assert(!url.username && !url.password, "Do not supply credentials in endpoints");
}
const provider = new EsploraProvider(esploraUrl, { forcePolling: true, pollingInterval: 500 });
const watchdog = setTimeout(() => {
    console.error(`Experiment phase ${phase} timed out`);
    process.exit(1);
}, 240_000);
watchdog.unref();

function cli(...args) {
    return execFileSync(process.execPath, ["../../regtest/regtest.mjs", ...args], {
        encoding: "utf8",
        timeout: 90_000,
        stdio: ["ignore", "pipe", "pipe"],
    })
        .replace(/\u001b\[[0-9;]*m/g, "")
        .split("\n")
        .filter((line) => !/^\[\d[^\]]*\] /.test(line))
        .join("\n")
        .trim();
}

const rpc = (...args) => cli("rpc", ...args);
const mine = (count = 1) => cli("mine", String(count));
const outpoints = (coins) => coins.map((coin) => `${coin.txid}:${coin.vout}`).sort();
const json = async (name) => JSON.parse(await readFile(resolve(dir, name), "utf8"));
async function save(name, value) {
    await writeFile(resolve(dir, name), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
}
async function record(value) {
    const result = { revision, phase, observedAt: new Date().toISOString(), ...value };
    await save(`${phase}.result.json`, result);
    console.log(JSON.stringify(result));
}
async function waitFor(check, label) {
    const deadline = Date.now() + 45_000;
    while (Date.now() < deadline) {
        if (await check()) return;
        await new Promise((done) => setTimeout(done, 500));
    }
    throw new Error(`Timed out waiting for ${label}`);
}
async function assertArkUnavailable() {
    await assert.rejects(
        fetch(`${arkUrl}/v1/info`, { signal: AbortSignal.timeout(2000) }),
        "Stop the experiment's Ark services before running this phase",
    );
}

function repositories() {
    const path = resolve(dir, "wallet.sqlite");
    if (phase !== "seed") assert(existsSync(path), "The persisted wallet database is required");
    const db = new DatabaseSync(path);
    const executor = {
        run: async (sql, params = []) => {
            db.prepare(sql).run(...params);
        },
        get: async (sql, params = []) => db.prepare(sql).get(...params),
        all: async (sql, params = []) => db.prepare(sql).all(...params),
    };
    return {
        db,
        storage: {
            walletRepository: new SQLiteWalletRepository(executor),
            contractRepository: new SQLiteContractRepository(executor),
            virtualTxRepository: new SQLiteVirtualTxRepository(executor),
            exitDataCapture: { mode: "full" },
        },
    };
}

async function openWallet(secrets, storage) {
    const identity = SingleKey.fromHex(secrets.wallet);
    const wallet = await Wallet.create({
        identity,
        arkServerUrl: arkUrl,
        onchainProvider: provider,
        storage,
        settlementConfig: false,
    });
    const feeWallet = await OnchainWallet.create(identity, "regtest", provider);
    return { wallet, feeWallet };
}

async function seed() {
    await mkdir(dir, { recursive: true });
    assert.deepEqual(await readdir(dir), [], "Seed phase requires an empty directory");
    const secrets = {
        wallet: randomBytes(32).toString("hex"),
        destination: randomBytes(32).toString("hex"),
    };
    const { db, storage } = repositories();
    const { wallet, feeWallet } = await openWallet(secrets, storage);
    try {
        assert.equal(wallet.getProviderConnectionState().mode, "online");
        const destination = await OnchainWallet.create(
            SingleKey.fromHex(secrets.destination),
            "regtest",
            provider,
        );
        const address = await wallet.getAddress();
        const note = cli("arkd", "note", "--amount", "200000");
        cli("ark", "redeem-notes", "-n", note, "--password", "secret");
        cli("ark", "send", "--to", address, "--amount", "120000", "--password", "secret");
        await waitFor(async () => (await wallet.getVtxos()).length > 0, "received VTXO");
        const received = await wallet.getVtxos();
        await wallet.settle({
            inputs: received,
            outputs: [{ address, amount: BigInt(received.reduce((sum, coin) => sum + coin.value, 0)) }],
        });
        // Add a real offchain transfer so recovery needs more than a settled root.
        await wallet.send({ address, amount: 90_000 });
        await waitFor(async () => {
            const coins = await wallet.getVtxos();
            if (!coins.length) return false;
            const captured = await Promise.all(coins.map((coin) => storage.virtualTxRepository.hasBranch(coin)));
            return captured.every(Boolean);
        }, "complete exit-data capture");
        cli("faucet", feeWallet.address, "0.00150000", "--confirm");
        await waitFor(async () => (await feeWallet.getCoins()).some((coin) => coin.status.confirmed), "fee funding");
        const coins = await wallet.getVtxos();
        assert.equal(coins.length, 2);
        assert.equal(coins.reduce((sum, coin) => sum + coin.value, 0), 120_000);
        const quote = await UnilateralExit.estimate({
            wallet,
            onchainWallet: feeWallet,
            sweepAddress: destination.address,
            feeRate: 2,
        });
        assert(quote.vtxos.length > 0 && quote.vtxos.every((coin) => !coin.skipped));
        assert.equal(quote.shortfallSats, 0);
        await save("secrets.json", secrets);
        await save("public.json", { outpoints: outpoints(coins), destination: destination.address });
        await record({
            result: "online_control_passed",
            outpoints: outpoints(coins),
            values: coins.map((coin) => coin.value),
            quote: quote.totals,
            retained: ["wallet key", "wallet/contract SQLite state", "full virtual transaction data", "confirmed fee funds"],
        });
    } finally {
        await wallet.dispose();
        db.close();
    }
}

async function recover() {
    await assertArkUnavailable();
    const secrets = await json("secrets.json");
    const original = await json("public.json");
    const { db, storage } = repositories();
    if (phase === "missing") await storage.virtualTxRepository.clear();
    const { wallet, feeWallet } = await openWallet(secrets, storage);
    try {
        assert.equal(wallet.serverInfoSource, "cache");
        assert.equal(wallet.getProviderConnectionState().mode, "degraded");
        const coins = await wallet.getVtxos();
        assert.deepEqual(outpoints(coins), original.outpoints);
        const options = { wallet, onchainWallet: feeWallet, sweepAddress: original.destination, feeRate: 2 };
        if (phase === "missing") {
            assert.equal(db.prepare("SELECT count(*) AS n FROM ark_virtual_txs").get().n, 0);
            let failure;
            let causeCode;
            let failedPath;
            await assert.rejects(async () => {
                try {
                    await UnilateralExit.estimate(options);
                } catch (error) {
                    failure = String(error.message);
                    throw error;
                }
            }, (error) => {
                assert(error instanceof ProviderUnavailableError);
                assert(coins.some((coin) => error.cause?.url?.includes(`/vtxo/${coin.txid}/${coin.vout}/chain`)));
                assert.equal(error.cause?.cause?.cause?.code, "ECONNREFUSED");
                causeCode = error.cause.cause.cause.code;
                failedPath = new URL(error.cause.url).pathname;
                return true;
            });
            await record({ result: "cached_balance_survives_but_exit_data_is_required", outpoints: outpoints(coins), failure, causeCode, failedPath });
            return;
        }
        const quote = await UnilateralExit.estimate(options);
        assert.equal(quote.shortfallSats, 0);
        assert(quote.vtxos.length > 0 && quote.vtxos.every((coin) => !coin.skipped));
        const pkg = await UnilateralExit.prepare(options);
        assert.equal(pkg.network, "regtest");
        assert.equal(pkg.vtxos.length, original.outpoints.length);
        assert(pkg.vtxos.every((coin) => !coin.skipped));
        assert(pkg.steps.some((step) => step.kind === "sweep"));
        await writeFile(resolve(dir, "exit-package.json"), serializeExitPackage(pkg), { mode: 0o600 });
        mine();
        await assertArkUnavailable();
        await record({ result: "prepared_from_persistent_state_with_ark_unavailable", totals: pkg.totals, outpoints: outpoints(coins) });
    } finally {
        await wallet.dispose();
        db.close();
    }
}

async function execute() {
    await assertArkUnavailable();
    assert(!existsSync(resolve(dir, "secrets.json")), "Executor directory must contain no original keys");
    assert(!existsSync(resolve(dir, "wallet.sqlite")), "Executor must use only the exported package");
    const pkg = deserializeExitPackage(await readFile(resolve(dir, "exit-package.json"), "utf8"));
    assert.equal(pkg.network, "regtest");
    const events = [];
    const executor = new UnilateralExit.Executor(pkg, provider, { pollIntervalMs: 500 });
    for await (const event of executor) {
        events.push(event);
        assert.notEqual(event.status, "failed", JSON.stringify(event));
        if (event.status === "broadcast") mine();
        if (event.status === "waiting_csv") {
            assert(event.maturesAtHeight, "This experiment covers block-based timelocks only");
            const tip = Number(rpc("getblockcount"));
            mine(Math.max(1, event.maturesAtHeight - tip + 1));
        }
    }
    const sweeps = events.filter((event) => event.kind === "sweep" && event.status === "confirmed");
    assert.equal(sweeps.length, pkg.steps.filter((step) => step.kind === "sweep").length);
    assert(sweeps.length > 0);
    await waitFor(async () => {
        const coins = await provider.getCoins(pkg.sweepAddress);
        return coins.every((coin) => coin.status.confirmed) && coins.reduce((sum, coin) => sum + coin.value, 0) === pkg.totals.recoveredSats;
    }, "confirmed sweep outputs");
    await assertArkUnavailable();
    await record({ result: "keyless_fresh_process_exit_confirmed", confirmedSweeps: sweeps.length, recoveredSats: pkg.totals.recoveredSats, events });
}

async function spend() {
    await assertArkUnavailable();
    const secrets = await json("secrets.json");
    const receiver = await OnchainWallet.create(SingleKey.fromHex(secrets.destination), "regtest", provider);
    const transaction = await receiver.send({ address: rpc("getnewaddress"), amount: 1000, feeRate: 2 });
    mine();
    await waitFor(async () => (await provider.getTxStatus(transaction)).confirmed, "spend of recovered output");
    const pkg = deserializeExitPackage(await readFile(resolve(dir, "exit-package.json"), "utf8"));
    const sweepTxids = pkg.steps.filter((step) => step.kind === "sweep").map((step) => step.txid);
    const spendingTx = (await provider.getTransactions(receiver.address)).find((tx) => tx.txid === transaction);
    assert(spendingTx?.vin?.some((input) => sweepTxids.includes(input.txid)));
    await record({ result: "recovered_output_spent_and_confirmed", transaction, spentSweepTxids: spendingTx.vin.filter((input) => sweepTxids.includes(input.txid)).map((input) => input.txid) });
}

// Verify both the node and the independently accessed explorer before creating keys.
assert.equal(JSON.parse(rpc("getblockchaininfo")).chain, "regtest");
const genesis = await fetch(`${esploraUrl}/block-height/0`, { signal: AbortSignal.timeout(5000) });
assert(genesis.ok);
assert.equal((await genesis.text()).trim(), rpc("getblockhash", "0"));
const height = Number(rpc("getblockcount"));
assert(height > 0, "Start and initialize the regtest stack first");
const expectedHash = rpc("getblockhash", String(height));
await waitFor(async () => {
    const block = await fetch(`${esploraUrl}/block-height/${height}`, { signal: AbortSignal.timeout(5000) });
    return block.ok && (await block.text()).trim() === expectedHash;
}, "explorer to match this regtest node above genesis");
try {
    if (phase === "seed") await seed();
    else if (phase === "missing" || phase === "prepare") await recover();
    else if (phase === "execute") await execute();
    else await spend();
} finally {
    clearTimeout(watchdog);
}
