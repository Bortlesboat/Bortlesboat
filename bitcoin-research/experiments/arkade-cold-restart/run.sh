#!/usr/bin/env bash
set -euo pipefail

# Run only against a dedicated, already-started arkade-regtest stack.
SDK=$(cd "${1:?Usage: bash run.sh /path/to/pinned/ts-sdk}" && pwd)
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PIN=8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1
REGTEST_PIN=e3b542f3c219b18be861e06761a0e4c5d565bb1a
test "$(git -C "$SDK" rev-parse HEAD)" = "$PIN" || { echo 'SDK revision differs from the experiment pin' >&2; exit 1; }
test -z "$(git -C "$SDK" status --porcelain -- packages/ts-sdk/src packages/ts-sdk/package.json pnpm-lock.yaml)" || { echo 'SDK source or dependencies have local changes' >&2; exit 1; }
test "$(git -C "$SDK/regtest" rev-parse HEAD)" = "$REGTEST_PIN" || { echo 'Regtest revision differs from the experiment pin' >&2; exit 1; }
test -z "$(git -C "$SDK/regtest" status --porcelain)" || { echo 'Regtest checkout has local changes' >&2; exit 1; }
case "${REGTEST_PROJECT:-}" in bitcoin-recovery-*) ;; *) echo 'Use a dedicated bitcoin-recovery-* Compose project' >&2; exit 1 ;; esac
case "${REGTEST_CONTAINER_PREFIX:-}" in btc-recovery-*) ;; *) echo 'Use a dedicated btc-recovery-* container prefix' >&2; exit 1 ;; esac
for service in arkd arkd-wallet; do
    container="${REGTEST_CONTAINER_PREFIX}${service}"
    project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
    test "$project" = "$REGTEST_PROJECT" || { echo "Unexpected owner of $container" >&2; exit 1; }
    test "$(docker inspect --format '{{.State.Running}}' "$container")" = true || { echo "$container must be running initially" >&2; exit 1; }
done

# Rebuild the code actually imported by the experiment, after checking its source.
corepack pnpm -C "$SDK/packages/ts-sdk" run build

RUN=$(mktemp -d "${TMPDIR:-/tmp}/arkade-cold-restart.XXXXXX")
RUNNER=$(mktemp "$SDK/packages/ts-sdk/.cold-restart-XXXXXX.mjs")
trap 'rm -f -- "$RUNNER"' EXIT
cp "$HERE/cold-restart.mjs" "$RUNNER"
cd "$SDK/packages/ts-sdk"
node "$RUNNER" seed "$RUN/seed"
cp -R "$RUN/seed" "$RUN/missing"
cp -R "$RUN/seed" "$RUN/full"

# These two containers were ownership-checked above. Bitcoin and its explorer stay up.
docker stop "${REGTEST_CONTAINER_PREFIX}arkd" "${REGTEST_CONTAINER_PREFIX}arkd-wallet" >/dev/null
node "$RUNNER" missing "$RUN/missing"
node "$RUNNER" prepare "$RUN/full"
mkdir "$RUN/keyless"
cp "$RUN/full/exit-package.json" "$RUN/keyless/exit-package.json"
node "$RUNNER" execute "$RUN/keyless"
node "$RUNNER" spend "$RUN/full"

node --input-type=module - "$RUN" <<'JS'
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const root = process.argv[2];
const files = ['seed/seed.result.json', 'missing/missing.result.json', 'full/prepare.result.json', 'keyless/execute.result.json', 'full/spend.result.json'];
const results = files.map((file) => JSON.parse(readFileSync(join(root, file), 'utf8')));
writeFileSync(join(root, 'results.json'), JSON.stringify({ schemaVersion: 1, results }, null, 2) + '\n');
console.log(`Completed all five phases. Result: ${join(root, 'results.json')}`);
JS
printf 'Private fixtures (including disposable regtest keys): %s\n' "$RUN"
printf 'The dedicated Ark services remain stopped; use the regtest CLI to stop the remaining stack.\n'
